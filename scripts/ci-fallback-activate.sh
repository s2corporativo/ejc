#!/usr/bin/env bash
# Ativa/desativa o fallback local do EJC em máquina NÃO produtiva.
# A troca é transacional e recuperável após crash: required status checks,
# watcher, hooks e drain são reconciliados por journal durável.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MODE="${1:-}"
REPO="${EJC_REPO:-s2corporativo/ejc}"
FALLBACK_APP_ID="${EJC_FALLBACK_APP_ID:-}"
INSTALLATION_ID="${EJC_FALLBACK_INSTALLATION_ID:-}"
APP_KEY_FILE="${EJC_FALLBACK_APP_PRIVATE_KEY_FILE:-}"
UNIT_DIR="${HOME}/.config/systemd/user"
UNIT="$UNIT_DIR/ejc-ci-fallback.service"
CRON_MARK='# EJC_CI_FALLBACK_998'
CACHE_ROOT="${EJC_CI_STATE_ROOT:-${XDG_CACHE_HOME:-${HOME}/.cache}/ejc-ci-fallback}"
LOG_DIR="$CACHE_ROOT"
WATCHER_PATH="${EJC_FALLBACK_PATH:-$PATH}"
HOOKS_BACKUP="$LOG_DIR/core-hooks-path.before"
LOCK_FILE="$LOG_DIR/watcher.lock"
DRAIN_FILE="$LOG_DIR/draining"
ACTIVE_FILE="$LOG_DIR/active.json"
PROTECTION_BACKUP="$LOG_DIR/required-status-checks.before.json"
JOURNAL_FILE="$LOG_DIR/activation-transaction.json"
JOURNAL_TOOL="$ROOT/scripts/ci_activation_journal.py"
mkdir -p "$LOG_DIR"
chmod 700 "$LOG_DIR" 2>/dev/null || true

fail(){ echo "[fallback-activate] ERRO: $*" >&2; exit 1; }
ok(){ echo "[fallback-activate] ok: $*"; }

case "$(realpath "$ROOT" 2>/dev/null || printf '%s' "$ROOT")" in
  /opt/ejc|/opt/ejc/*) fail "recusado em /opt/ejc (produção)" ;;
esac
[ "$(id -u)" -ne 0 ] || fail "não execute como root"
[ "${APP_ENV:-}" != "production" ] && [ "${EJC_ENV:-}" != "production" ] \
  || fail "ambiente de produção ativo"
[ ! -e /opt/ejc/.deployed_sha ] && [ ! -e /opt/ejc/.env ] \
  || fail "host contém marcadores da instalação produtiva /opt/ejc"

case "$WATCHER_PATH$APP_KEY_FILE" in
  *$'\n'*|*$'\r'*|*"'"*|*'"'*|*'\'*|*%*) fail "PATH/caminho de chave contém caractere inseguro para scheduler" ;;
esac
case "$ROOT$LOG_DIR$REPO" in
  *$'\n'*|*$'\r'*|*"'"*|*'"'*|*'\'*|*%*|*[[:space:]]*) fail "ROOT/LOG_DIR/REPO contém caractere inseguro para scheduler" ;;
esac

journal_begin() {
  local scheduler="$1"
  python3 "$JOURNAL_TOOL" begin \
    --state-root "$CACHE_ROOT" \
    --file "$JOURNAL_FILE" \
    --repo "$REPO" \
    --protection-backup "$PROTECTION_BACKUP" \
    --hooks-backup "$HOOKS_BACKUP" \
    --scheduler "$scheduler"
}

journal_phase() {
  python3 "$JOURNAL_TOOL" phase \
    --state-root "$CACHE_ROOT" \
    --file "$JOURNAL_FILE" \
    --phase "$1"
}

journal_clear() {
  python3 "$JOURNAL_TOOL" clear \
    --state-root "$CACHE_ROOT" \
    --file "$JOURNAL_FILE"
}

remove_cron() {
  command -v crontab >/dev/null 2>&1 || return 0
  local atual filtrado
  atual="$(crontab -l 2>/dev/null || true)"
  filtrado="$(printf '%s\n' "$atual" | grep -vF "$CRON_MARK" || true)"
  printf '%s\n' "$filtrado" | crontab - || return 1
}

remove_watcher() {
  local rc=0 unit_aplicavel=0
  if command -v systemctl >/dev/null 2>&1; then
    if [ -f "$UNIT" ] \
      || systemctl --user is-active --quiet ejc-ci-fallback.service 2>/dev/null \
      || systemctl --user is-enabled --quiet ejc-ci-fallback.service 2>/dev/null; then
      unit_aplicavel=1
    fi
    if [ "$unit_aplicavel" -eq 1 ]; then
      if ! systemctl --user disable --now ejc-ci-fallback.service >/dev/null 2>&1; then
        return 1
      fi
    fi
    if [ -e "$UNIT" ]; then
      rm -f "$UNIT" || rc=1
      systemctl --user daemon-reload >/dev/null 2>&1 || rc=1
    fi
  elif [ -e "$UNIT" ]; then
    rc=1
  fi
  remove_cron || rc=1
  return "$rc"
}

restore_hooks_path() {
  [ -f "$HOOKS_BACKUP" ] || return 0
  local previous
  previous="$(cat "$HOOKS_BACKUP")"
  if [ "$previous" = "__UNSET__" ]; then
    git config --local --unset-all core.hooksPath >/dev/null 2>&1 || true
  else
    git config --local core.hooksPath "$previous" || return 1
  fi
  rm -f "$HOOKS_BACKUP" || return 1
}

scheduler_present() {
  if command -v systemctl >/dev/null 2>&1; then
    systemctl --user is-active --quiet ejc-ci-fallback.service 2>/dev/null && return 0
  fi
  command -v crontab >/dev/null 2>&1 \
    && (crontab -l 2>/dev/null || true) | grep -qF "$CRON_MARK" \
    && return 0
  return 1
}

fallback_protection_is_active() {
  local status
  status="$(bash scripts/governanca/branch-protection.sh --verificar 2>/dev/null)" || return 1
  printf '%s' "$status" | jq -e --argjson app_id "$FALLBACK_APP_ID" '
    .strict == true and
    (.checks | length) == 1 and
    .checks[0].context == "EJC Local Full Gate" and
    .checks[0].app_id == $app_id
  ' >/dev/null 2>&1
}

write_active_state() {
  local scheduler="$1" tmp
  tmp="$ACTIVE_FILE.tmp.$$"
  umask 077
  jq -n \
    --arg repo "$REPO" \
    --arg app_id "$FALLBACK_APP_ID" \
    --arg installation_id "$INSTALLATION_ID" \
    --arg scheduler "$scheduler" \
    --arg protection_backup "$PROTECTION_BACKUP" \
    --arg state_root "$CACHE_ROOT" \
    --arg activated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{schema:1,repo:$repo,app_id:$app_id,installation_id:$installation_id,scheduler:$scheduler,protection_backup:$protection_backup,state_root:$state_root,activated_at:$activated_at}' > "$tmp"
  chmod 600 "$tmp" 2>/dev/null || true
  python3 - "$tmp" "$ACTIVE_FILE" <<'PY'
import os, sys
src, dst = sys.argv[1:]
with open(src, "rb") as fh:
    os.fsync(fh.fileno())
os.replace(src, dst)
fd = os.open(os.path.dirname(dst), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(fd)
finally:
    os.close(fd)
PY
}

create_drain_marker() {
  local tmp="$DRAIN_FILE.tmp.$$"
  umask 077
  printf 'draining %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$tmp"
  chmod 600 "$tmp" 2>/dev/null || true
  python3 - "$tmp" "$DRAIN_FILE" <<'PY'
import os, sys
src, dst = sys.argv[1:]
with open(src, "rb") as fh:
    os.fsync(fh.fileno())
os.replace(src, dst)
fd = os.open(os.path.dirname(dst), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(fd)
finally:
    os.close(fd)
PY
}

recover_incomplete_transaction() {
  [ -s "$JOURNAL_FILE" ] || return 0
  python3 "$JOURNAL_TOOL" show --state-root "$CACHE_ROOT" --file "$JOURNAL_FILE" >/dev/null || return 1
  create_drain_marker || return 1
  exec 7>"$LOCK_FILE"
  flock -w 120 7 || return 1

  # Se existe snapshot de proteção, ele é a autoridade. Falha de API preserva
  # journal + drain + watcher + snapshot para retry idempotente.
  if [ -s "$PROTECTION_BACKUP" ]; then
    command -v gh >/dev/null 2>&1 || return 1
    gh auth status >/dev/null 2>&1 || return 1
    if ! EJC_BRANCH_PROTECTION_BACKUP="$PROTECTION_BACKUP" \
        bash scripts/governanca/branch-protection.sh --restore; then
      return 1
    fi
  fi

  remove_watcher || return 1
  restore_hooks_path || return 1
  rm -f "$ACTIVE_FILE"
  [ ! -e "$PROTECTION_BACKUP" ] || rm -f "$PROTECTION_BACKUP" || return 1
  rm -f "$DRAIN_FILE" || return 1
  journal_clear || return 1
  return 0
}

if [ "$MODE" = "--status" ]; then
  if [ -e "$JOURNAL_FILE" ]; then
    if python3 "$JOURNAL_TOOL" show --state-root "$CACHE_ROOT" --file "$JOURNAL_FILE" >/dev/null 2>&1; then
      printf '[fallback-activate] state=recovery_required journal=%s draining=%s\n' \
        "$JOURNAL_FILE" "$([ -e "$DRAIN_FILE" ] && echo yes || echo no)"
    else
      echo "[fallback-activate] ERRO: journal residual inválido/adulterado; recovery manual seguro requerido" >&2
    fi
    exit 1
  fi
  if [ -s "$ACTIVE_FILE" ]; then
    printf '[fallback-activate] state=active scheduler=%s draining=%s\n' \
      "$(jq -r '.scheduler // "unknown"' "$ACTIVE_FILE")" \
      "$([ -e "$DRAIN_FILE" ] && echo yes || echo no)"
    scheduler_present || { echo "[fallback-activate] ERRO: active.json existe, mas scheduler não está ativo" >&2; exit 1; }
    exit 0
  fi
  printf '[fallback-activate] state=inactive draining=%s\n' "$([ -e "$DRAIN_FILE" ] && echo yes || echo no)"
  exit 0
fi

if [ "$MODE" = "--disable" ]; then
  for c in git jq flock python3; do command -v "$c" >/dev/null 2>&1 || fail "$c ausente"; done
  if [ -e "$JOURNAL_FILE" ]; then
    recover_incomplete_transaction \
      || fail "recovery incompleto; journal/drain/snapshot preservados para nova tentativa"
    ok "transação incompleta recuperada idempotentemente; fallback inativo"
    exit 0
  fi

  [ -s "$ACTIVE_FILE" ] || fail "fallback não possui estado ativo registrado; nada foi alterado"
  [ -s "$PROTECTION_BACKUP" ] || fail "snapshot anterior de required status checks ausente"
  command -v gh >/dev/null 2>&1 || fail "gh ausente"
  gh auth status >/dev/null 2>&1 || fail "gh não autenticado neste host"
  scheduler="$(jq -r '.scheduler // "unknown"' "$ACTIVE_FILE")"
  journal_begin "$scheduler"
  create_drain_marker
  journal_phase draining

  exec 8>"$LOCK_FILE"
  if ! flock -w 120 8; then
    fail "watcher não drenou em 120s; journal/drain preservados para recovery"
  fi

  if ! EJC_BRANCH_PROTECTION_BACKUP="$PROTECTION_BACKUP" \
      bash scripts/governanca/branch-protection.sh --restore; then
    fail "não foi possível restaurar required status checks; journal/drain/watcher preservados"
  fi
  journal_phase protection

  if ! remove_watcher; then
    fail "checks anteriores restaurados, mas watcher não pôde ser removido; drain/journal preservados"
  fi
  if ! restore_hooks_path; then
    fail "watcher removido e checks restaurados, mas core.hooksPath não pôde ser restaurado; journal preservado"
  fi
  rm -f "$ACTIVE_FILE" "$PROTECTION_BACKUP" "$DRAIN_FILE"
  journal_phase active
  journal_clear
  ok "fallback desativado transacionalmente; required status checks anteriores restaurados"
  exit 0
fi

[ "$MODE" = "--enable" ] || fail "uso: $0 --enable | --disable | --status"

[ ! -e "$JOURNAL_FILE" ] || fail "journal incompleto presente; execute --disable para recovery antes de nova ativação"
[[ "$FALLBACK_APP_ID" =~ ^[1-9][0-9]*$ ]] || fail "EJC_FALLBACK_APP_ID numérico (>0) obrigatório"
[[ "$INSTALLATION_ID" =~ ^[1-9][0-9]*$ ]] || fail "EJC_FALLBACK_INSTALLATION_ID numérico (>0) obrigatório"
[ -n "$APP_KEY_FILE" ] || fail "EJC_FALLBACK_APP_PRIVATE_KEY_FILE obrigatório"
for c in git gh jq python3 node npm psql flock docker openssl curl; do command -v "$c" >/dev/null 2>&1 || fail "$c ausente"; done
docker info >/dev/null 2>&1 || fail "Docker não acessível pelo usuário atual"
if docker ps --format '{{.Names}}' 2>/dev/null | grep -Eq '^(ejc_backend|ejc_worker|ejc_db|ejc_frontend|ejc_redis)$'; then
  fail "containers canônicos do EJC ativos; host não é elegível para CI de PR"
fi
gh auth status >/dev/null 2>&1 || fail "gh de usuário não autenticado neste host"

if [ -s "$ACTIVE_FILE" ]; then
  if scheduler_present && fallback_protection_is_active && [ ! -e "$DRAIN_FILE" ]; then
    ok "fallback já está ativo e consistente; nenhuma configuração foi sobrescrita"
    exit 0
  fi
  fail "estado ativo existe, mas scheduler/proteção/drain estão inconsistentes; execute --status e corrija antes de nova ativação"
fi
[ ! -e "$DRAIN_FILE" ] || fail "drain residual presente; finalize a desativação anterior"
[ ! -e "$PROTECTION_BACKUP" ] || fail "snapshot residual de proteção presente; recuse sobrescrita"

PYVER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [ "$PYVER" != "3.11" ] && ! command -v python3.11 >/dev/null 2>&1; then fail "Python 3.11 ausente"; fi
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
[ "$NODE_MAJOR" = "22" ] || fail "Node 22 requerido; encontrado $(node --version)"

[ "$(git branch --show-current)" = "main" ] || fail "ative somente a partir da branch main"
[ -z "$(git status --porcelain)" ] || fail "checkout local possui alterações; limpe-o antes da ativação"
git fetch --quiet origin main || fail "não foi possível atualizar origin/main"
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || fail "main local não corresponde à origin/main"

# shellcheck source=github-app-auth.sh
source scripts/github-app-auth.sh
_ejc_validate_private_key >/dev/null || fail "chave privada do GitHub App não atende à política local"
ejc_github_app_clear

cron_persistente() {
  command -v crontab >/dev/null 2>&1 || return 1
  if command -v pgrep >/dev/null 2>&1; then
    pgrep -x cron >/dev/null 2>&1 && return 0
    pgrep -x crond >/dev/null 2>&1 && return 0
  fi
  if command -v systemctl >/dev/null 2>&1; then
    systemctl is-active --quiet cron 2>/dev/null && return 0
    systemctl is-active --quiet crond 2>/dev/null && return 0
  fi
  return 1
}

systemd_user_persistente() {
  command -v systemctl >/dev/null 2>&1 || return 1
  command -v loginctl >/dev/null 2>&1 || return 1
  systemctl --user show-environment >/dev/null 2>&1 || return 1
  [ "$(loginctl show-user "$(id -un)" -p Linger --value 2>/dev/null || true)" = "yes" ]
}

SCHEDULER=""
if cron_persistente; then
  SCHEDULER=cron
elif systemd_user_persistente; then
  SCHEDULER=systemd
else
  fail "sem scheduler persistente: requer cron/crond ativo ou systemd --user com linger=yes"
fi
ok "scheduler persistente selecionado: $SCHEDULER"

for script in \
  scripts/ci-local.sh \
  scripts/ci-fallback.sh \
  scripts/ci-fallback-watch.sh \
  scripts/ci-fallback-activate.sh \
  scripts/github-app-auth.sh \
  scripts/governanca/ci-local-governanca.sh \
  scripts/governanca/branch-protection.sh; do
  bash -n "$script" || fail "sintaxe inválida em $script"
done
python3 -m py_compile "$JOURNAL_TOOL" || fail "journal helper inválido"
ok "sintaxe dos componentes do fallback"

log_preflight="$LOG_DIR/activation-preflight.log"
if ! EJC_CI_STATE_ROOT="$CACHE_ROOT" EJC_ALLOW_PYTHON_MISMATCH=0 \
    bash scripts/ci-local.sh fast >"$log_preflight" 2>&1; then
  tail -n 100 "$log_preflight" >&2 || true
  fail "preflight local falhou; branch protection não foi alterada"
fi
ok "preflight local aprovado antes da alteração da branch protection"

PRE_SHA="$(git rev-parse HEAD)"
PRE_PAYLOAD="$(jq -cn --arg sha "$PRE_SHA" '{name:"EJC Local Activation Preflight",head_sha:$sha,status:"completed",conclusion:"neutral",output:{title:"EJC Local Activation Preflight",summary:"preflight de credencial antes da troca de required status checks"}}')"
PRE_RESULT="$(printf '%s' "$PRE_PAYLOAD" | ejc_github_app_gh_api -X POST "repos/$REPO/check-runs" -H 'Accept: application/vnd.github+json' --input - 2>/dev/null)" \
  || fail "credencial do GitHub App não possui acesso funcional à Checks API"
[ "$(printf '%s' "$PRE_RESULT" | jq -r '.app.id // -1')" = "$FALLBACK_APP_ID" ] \
  || fail "Check Run de preflight foi emitido por App diferente do esperado"
ejc_github_app_clear
ok "GitHub App validado antes da alteração da proteção"

install_watcher() {
  if [ "$SCHEDULER" = "systemd" ]; then
    mkdir -p "$UNIT_DIR"
    cat > "$UNIT" <<UNIT
[Unit]
Description=EJC CI fallback watcher (worktree isolado)
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
Environment="PATH=$WATCHER_PATH"
Environment="EJC_REPO=$REPO"
Environment="EJC_CI_STATE_ROOT=$CACHE_ROOT"
Environment="EJC_FALLBACK_DRAIN_FILE=$DRAIN_FILE"
Environment="EJC_FALLBACK_APP_ID=$FALLBACK_APP_ID"
Environment="EJC_FALLBACK_INSTALLATION_ID=$INSTALLATION_ID"
Environment="EJC_FALLBACK_APP_PRIVATE_KEY_FILE=$APP_KEY_FILE"
Environment="EJC_FALLBACK_AUTO_MERGE=1"
Environment="EJC_ALLOW_PYTHON_MISMATCH=0"
ExecStart=/usr/bin/flock -n $LOCK_FILE /usr/bin/env bash $ROOT/scripts/ci-fallback-watch.sh
Restart=on-failure
RestartSec=20
StandardOutput=append:$LOG_DIR/watcher.log
StandardError=append:$LOG_DIR/watcher.log

[Install]
WantedBy=default.target
UNIT
    systemctl --user daemon-reload
    systemctl --user enable --now ejc-ci-fallback.service
    systemctl --user is-enabled --quiet ejc-ci-fallback.service
    systemctl --user is-active --quiet ejc-ci-fallback.service
    ok "watcher persistente ativado via systemd --user"
  else
    LINE="*/5 * * * * cd '$ROOT' && /usr/bin/env PATH='$WATCHER_PATH' EJC_REPO='$REPO' EJC_CI_STATE_ROOT='$CACHE_ROOT' EJC_FALLBACK_DRAIN_FILE='$DRAIN_FILE' EJC_FALLBACK_APP_ID='$FALLBACK_APP_ID' EJC_FALLBACK_INSTALLATION_ID='$INSTALLATION_ID' EJC_FALLBACK_APP_PRIVATE_KEY_FILE='$APP_KEY_FILE' EJC_FALLBACK_AUTO_MERGE=1 EJC_ALLOW_PYTHON_MISMATCH=0 flock -n '$LOCK_FILE' bash '$ROOT/scripts/ci-fallback-watch.sh' --once >> '$LOG_DIR/watcher.log' 2>&1 $CRON_MARK"
    { crontab -l 2>/dev/null || true; echo "$LINE"; } | crontab -
    (crontab -l 2>/dev/null || true) | grep -qF "$CRON_MARK"
    ok "watcher persistente ativado via cron (5 min, lock exclusivo)"
  fi
}

# A partir daqui existe mutação persistente. O journal é criado antes dela e o
# drain impede qualquer promoção enquanto a transação não chegar a active.
journal_begin "$SCHEDULER"
create_drain_marker
journal_phase draining

rollback_activation() {
  local rc=$?
  trap - EXIT
  if [ "$rc" -ne 0 ]; then
    recover_incomplete_transaction >/dev/null 2>&1 || true
  fi
  exit "$rc"
}
trap rollback_activation EXIT

remove_watcher || fail "não foi possível limpar watcher órfão anterior"
install_watcher
journal_phase watcher

if git config --local --get core.hooksPath >/dev/null 2>&1; then
  git config --local --get core.hooksPath > "$HOOKS_BACKUP"
else
  printf '%s\n' '__UNSET__' > "$HOOKS_BACKUP"
fi
chmod 600 "$HOOKS_BACKUP" 2>/dev/null || true
git config --local core.hooksPath .githooks
journal_phase hooks

EJC_FALLBACK_AUTHORIZATION=998 \
EJC_FALLBACK_APP_ID="$FALLBACK_APP_ID" \
EJC_BRANCH_PROTECTION_BACKUP="$PROTECTION_BACKUP" \
  bash scripts/governanca/branch-protection.sh --fallback
journal_phase protection
ok "required status checks apontados para EJC Local Full Gate/App $FALLBACK_APP_ID"

write_active_state "$SCHEDULER"
journal_phase commit

# Somente depois de estado ativo durável e proteção confirmada o executor é
# liberado. Crash antes desta remoção deixa drain+journal e exige recovery.
rm -f "$DRAIN_FILE"
journal_phase active
journal_clear
trap - EXIT
ok "fallback local autônomo ativo; GitHub Actions deixou de ser dependência de execução do CI"
