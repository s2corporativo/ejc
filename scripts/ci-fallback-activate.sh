#!/usr/bin/env bash
# Ativação transacional do fallback EJC em host dedicado NÃO produtivo.
# Estado: INACTIVE -> DRAINING -> ACTIVE. Em nenhuma transição required checks
# ficam apontando para um produtor inexistente.
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MODE="${1:-}"
REPO="${EJC_REPO:-s2corporativo/ejc}"
FALLBACK_APP_ID="${EJC_FALLBACK_APP_ID:-}"
INSTALLATION_ID="${EJC_FALLBACK_APP_INSTALLATION_ID:-${EJC_FALLBACK_INSTALLATION_ID:-}}"
APP_KEY_FILE="${EJC_FALLBACK_APP_PRIVATE_KEY_FILE:-}"
WORKER_USER="${EJC_CI_WORKER_USER:-}"
WORKER_ROOT="${EJC_CI_WORKER_ROOT:-/var/tmp/ejc-ci-worker}"
WATCHER_PATH="${EJC_FALLBACK_PATH:-/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin}"
CACHE_ROOT="${EJC_CI_STATE_ROOT:-${XDG_CACHE_HOME:-${HOME:-/tmp}/.cache}/ejc-ci-fallback}"
LOG_DIR="$CACHE_ROOT"
UNIT_DIR="${HOME}/.config/systemd/user"
UNIT="$UNIT_DIR/ejc-ci-fallback.service"
CRON_MARK='# EJC_CI_FALLBACK_998'
HOOKS_BACKUP="$LOG_DIR/core-hooks-path.before"
LOCK_FILE="$LOG_DIR/watcher.lock"
DRAIN_FILE="$LOG_DIR/draining"
ACTIVE_FILE="$LOG_DIR/active.json"
PROTECTION_BACKUP="$LOG_DIR/required-status-checks.before.json"

fail() { printf '[fallback-activate] ERRO: %s\n' "$*" >&2; exit 1; }
ok() { printf '[fallback-activate] ok: %s\n' "$*"; }

canon() {
  if command -v realpath >/dev/null 2>&1; then realpath -m "$1"; else printf '%s\n' "$1"; fi
}

ROOT_CANON="$(canon "$ROOT")"
HOME_CANON="$(canon "${HOME:-/__no_home__}")"
CACHE_CANON="$(canon "$CACHE_ROOT")"
case "$ROOT_CANON" in /opt/ejc|/opt/ejc/*) fail "recusado em /opt/ejc";; esac
case "$CACHE_CANON" in /|"$HOME_CANON"|/opt/ejc|/opt/ejc/*|"$ROOT_CANON"|"$ROOT_CANON"/*) fail "CACHE_ROOT inseguro: $CACHE_CANON";; esac
[ "$(id -u)" -ne 0 ] || fail "control plane não executa como root"
[ "${APP_ENV:-}" != production ] && [ "${EJC_ENV:-}" != production ] || fail "ambiente production ativo"
[ ! -e /opt/ejc/.deployed_sha ] && [ ! -e /opt/ejc/.env ] || fail "host contém marcadores da produção"
mkdir -p "$LOG_DIR"
chmod 0700 "$LOG_DIR"

validate_scheduler_value() {
  local label="$1" value="$2"
  case "$value" in
    *$'\n'*|*$'\r'*|*"'"*|*'"'*|*'\'*|*%*|*[[:space:]]*) fail "$label contém caractere inseguro para scheduler";;
  esac
}
for pair in "ROOT:$ROOT" "LOG_DIR:$LOG_DIR" "REPO:$REPO" "APP_KEY_FILE:$APP_KEY_FILE" "WATCHER_PATH:$WATCHER_PATH" "WORKER_USER:$WORKER_USER" "WORKER_ROOT:$WORKER_ROOT"; do
  validate_scheduler_value "${pair%%:*}" "${pair#*:}"
done

remove_cron() {
  command -v crontab >/dev/null 2>&1 || return 0
  local current filtered
  current="$(crontab -l 2>/dev/null || true)"
  filtered="$(printf '%s\n' "$current" | grep -vF "$CRON_MARK" || true)"
  printf '%s\n' "$filtered" | crontab -
}

remove_watcher() {
  local rc=0
  if command -v systemctl >/dev/null 2>&1; then
    if [ -f "$UNIT" ] || systemctl --user is-active --quiet ejc-ci-fallback.service 2>/dev/null || systemctl --user is-enabled --quiet ejc-ci-fallback.service 2>/dev/null; then
      systemctl --user disable --now ejc-ci-fallback.service >/dev/null 2>&1 || rc=1
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

scheduler_present() {
  if command -v systemctl >/dev/null 2>&1 && systemctl --user is-active --quiet ejc-ci-fallback.service 2>/dev/null; then return 0; fi
  command -v crontab >/dev/null 2>&1 && (crontab -l 2>/dev/null || true) | grep -qF "$CRON_MARK"
}

restore_hooks_path() {
  [ -f "$HOOKS_BACKUP" ] || return 0
  local previous
  previous="$(cat "$HOOKS_BACKUP")"
  if [ "$previous" = __UNSET__ ]; then
    git config --local --unset-all core.hooksPath >/dev/null 2>&1 || true
  else
    git config --local core.hooksPath "$previous"
  fi
  rm -f "$HOOKS_BACKUP"
}

backup_hooks_path() {
  [ ! -e "$HOOKS_BACKUP" ] || fail "backup residual de core.hooksPath existe"
  if git config --local --get core.hooksPath >/dev/null 2>&1; then
    git config --local --get core.hooksPath > "$HOOKS_BACKUP"
  else
    printf '%s\n' __UNSET__ > "$HOOKS_BACKUP"
  fi
  chmod 0600 "$HOOKS_BACKUP"
}

create_drain() {
  local tmp="$DRAIN_FILE.tmp.$$"
  printf 'draining %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$tmp"
  chmod 0600 "$tmp"
  mv "$tmp" "$DRAIN_FILE"
}

fallback_protection_is_active() {
  local status
  status="$(EJC_REPO="$REPO" bash scripts/governanca/branch-protection.sh --verificar 2>/dev/null)" || return 1
  printf '%s' "$status" | jq -e --argjson app_id "$FALLBACK_APP_ID" '.strict == true and (.checks|length)==1 and .checks[0].context=="EJC Local Full Gate" and .checks[0].app_id==$app_id' >/dev/null 2>&1
}

write_active_state() {
  local scheduler="$1" tmp="$ACTIVE_FILE.tmp.$$"
  jq -n --arg repo "$REPO" --arg app_id "$FALLBACK_APP_ID" --arg installation_id "$INSTALLATION_ID" --arg worker_user "$WORKER_USER" --arg worker_root "$WORKER_ROOT" --arg scheduler "$scheduler" --arg protection_backup "$PROTECTION_BACKUP" --arg activated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '{schema:2,repo:$repo,app_id:$app_id,installation_id:$installation_id,worker_user:$worker_user,worker_root:$worker_root,scheduler:$scheduler,protection_backup:$protection_backup,activated_at:$activated_at}' > "$tmp"
  chmod 0600 "$tmp"
  mv "$tmp" "$ACTIVE_FILE"
}

systemd_user_persistent() {
  command -v systemctl >/dev/null 2>&1 || return 1
  command -v loginctl >/dev/null 2>&1 || return 1
  systemctl --user show-environment >/dev/null 2>&1 || return 1
  [ "$(loginctl show-user "$(id -un)" -p Linger --value 2>/dev/null || true)" = yes ]
}

cron_persistent() {
  command -v crontab >/dev/null 2>&1 || return 1
  if command -v systemctl >/dev/null 2>&1; then
    systemctl is-active --quiet cron 2>/dev/null && return 0
    systemctl is-active --quiet crond 2>/dev/null && return 0
  fi
  command -v pgrep >/dev/null 2>&1 && { pgrep -x cron >/dev/null 2>&1 || pgrep -x crond >/dev/null 2>&1; }
}

install_watcher() {
  local scheduler="$1"
  if [ "$scheduler" = systemd ]; then
    mkdir -p "$UNIT_DIR"
    cat > "$UNIT" <<UNIT
[Unit]
Description=EJC CI fallback control plane
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
Environment="PATH=$WATCHER_PATH"
Environment="EJC_REPO=$REPO"
Environment="EJC_FALLBACK_APP_ID=$FALLBACK_APP_ID"
Environment="EJC_FALLBACK_APP_INSTALLATION_ID=$INSTALLATION_ID"
Environment="EJC_FALLBACK_APP_PRIVATE_KEY_FILE=$APP_KEY_FILE"
Environment="EJC_CI_WORKER_USER=$WORKER_USER"
Environment="EJC_CI_WORKER_ROOT=$WORKER_ROOT"
Environment="EJC_CI_STATE_ROOT=$CACHE_ROOT"
Environment="EJC_FALLBACK_DRAIN_FILE=$DRAIN_FILE"
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
    chmod 0600 "$UNIT"
    systemctl --user daemon-reload
    systemctl --user enable --now ejc-ci-fallback.service
    systemctl --user is-active --quiet ejc-ci-fallback.service
  else
    local line
    line="*/5 * * * * cd '$ROOT' && /usr/bin/env PATH='$WATCHER_PATH' EJC_REPO='$REPO' EJC_FALLBACK_APP_ID='$FALLBACK_APP_ID' EJC_FALLBACK_APP_INSTALLATION_ID='$INSTALLATION_ID' EJC_FALLBACK_APP_PRIVATE_KEY_FILE='$APP_KEY_FILE' EJC_CI_WORKER_USER='$WORKER_USER' EJC_CI_WORKER_ROOT='$WORKER_ROOT' EJC_CI_STATE_ROOT='$CACHE_ROOT' EJC_FALLBACK_DRAIN_FILE='$DRAIN_FILE' EJC_FALLBACK_AUTO_MERGE=1 EJC_ALLOW_PYTHON_MISMATCH=0 flock -n '$LOCK_FILE' bash '$ROOT/scripts/ci-fallback-watch.sh' --once >> '$LOG_DIR/watcher.log' 2>&1 $CRON_MARK"
    { crontab -l 2>/dev/null || true; echo "$line"; } | crontab -
    (crontab -l 2>/dev/null || true) | grep -qF "$CRON_MARK"
  fi
}

if [ "$MODE" = --status ]; then
  if [ -s "$ACTIVE_FILE" ]; then
    scheduler_present || fail "active.json existe, mas scheduler não está ativo"
    fallback_protection_is_active || fail "active.json existe, mas required check fallback não está ativo"
    printf '[fallback-activate] state=active scheduler=%s worker=%s draining=%s\n' "$(jq -r '.scheduler' "$ACTIVE_FILE")" "$(jq -r '.worker_user' "$ACTIVE_FILE")" "$([ -e "$DRAIN_FILE" ] && echo yes || echo no)"
  else
    printf '[fallback-activate] state=inactive draining=%s\n' "$([ -e "$DRAIN_FILE" ] && echo yes || echo no)"
  fi
  exit 0
fi

if [ "$MODE" = --disable ]; then
  for c in git gh jq flock; do command -v "$c" >/dev/null 2>&1 || fail "$c ausente"; done
  gh auth status >/dev/null 2>&1 || fail "gh não autenticado"
  [ -s "$ACTIVE_FILE" ] || fail "fallback não possui estado ativo registrado"
  [ -s "$PROTECTION_BACKUP" ] || fail "snapshot anterior de required checks ausente"

  create_drain
  exec 8>"$LOCK_FILE"
  if ! flock -w 120 8; then rm -f "$DRAIN_FILE"; fail "watcher não drenou em 120s"; fi

  if ! EJC_REPO="$REPO" EJC_BRANCH_PROTECTION_BACKUP="$PROTECTION_BACKUP" bash scripts/governanca/branch-protection.sh --restore; then
    rm -f "$DRAIN_FILE"
    fail "restauração da proteção falhou; watcher preservado e reativado"
  fi
  if ! remove_watcher; then
    fail "proteção restaurada, mas scheduler não pôde ser removido; drain mantido"
  fi
  restore_hooks_path || fail "proteção/watcher restaurados, mas hooks locais não"
  rm -f "$ACTIVE_FILE" "$PROTECTION_BACKUP" "$DRAIN_FILE"
  ok "fallback desativado; required checks anteriores restaurados exatamente"
  exit 0
fi

[ "$MODE" = --enable ] || fail "uso: $0 --enable | --disable | --status"
[[ "$FALLBACK_APP_ID" =~ ^[1-9][0-9]*$ ]] || fail "EJC_FALLBACK_APP_ID obrigatório"
[[ "$INSTALLATION_ID" =~ ^[1-9][0-9]*$ ]] || fail "EJC_FALLBACK_APP_INSTALLATION_ID obrigatório"
[ -n "$APP_KEY_FILE" ] || fail "EJC_FALLBACK_APP_PRIVATE_KEY_FILE obrigatório"
[ -n "$WORKER_USER" ] || fail "EJC_CI_WORKER_USER obrigatório"
for c in git gh jq python3 python3.11 node npm psql flock openssl curl sudo setfacl pgrep getent; do command -v "$c" >/dev/null 2>&1 || fail "$c ausente"; done
gh auth status >/dev/null 2>&1 || fail "gh de usuário não autenticado"

# Host dedicado: nenhum container persistente pode coexistir com o worker de PR.
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1 && [ -n "$(docker ps -q 2>/dev/null)" ]; then
  fail "host possui containers em execução; worker de PR exige host CI dedicado sem serviços co-residentes"
fi

[ ! -e "$ACTIVE_FILE" ] || { scheduler_present && fallback_protection_is_active && [ ! -e "$DRAIN_FILE" ] && { ok "fallback já ativo e consistente"; exit 0; }; fail "estado ativo inconsistente"; }
[ ! -e "$DRAIN_FILE" ] || fail "drain residual presente"
[ ! -e "$PROTECTION_BACKUP" ] || fail "snapshot residual de proteção presente"
[ "$(git branch --show-current)" = main ] || fail "ative somente a partir da main"
[ -z "$(git status --porcelain)" ] || fail "main local possui alterações"
git fetch --quiet origin main || fail "não foi possível atualizar origin/main"
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || fail "main local diferente de origin/main"
[ "$(node -p 'process.versions.node.split(".")[0]')" = 22 ] || fail "Node 22 requerido"
[ "$(python3.11 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" = 3.11 ] || fail "Python 3.11 requerido"

for script in scripts/ci-local.sh scripts/ci-fallback.sh scripts/ci-fallback-watch.sh scripts/ci-fallback-activate.sh scripts/ci-worker-isolation.sh scripts/github-app-auth.sh scripts/governanca/ci-local-governanca.sh scripts/governanca/branch-protection.sh; do
  bash -n "$script" || fail "sintaxe inválida: $script"
done
python3 -m py_compile scripts/ci_evidence.py || fail "ci_evidence.py inválido"

# Segurança do worker é provada antes de qualquer mutação da branch protection.
EJC_CI_WORKER_USER="$WORKER_USER" EJC_CI_WORKER_ROOT="$WORKER_ROOT" EJC_FALLBACK_APP_PRIVATE_KEY_FILE="$APP_KEY_FILE" bash scripts/ci-worker-isolation.sh preflight \
  || fail "worker dedicado não atende isolamento"
ok "worker dedicado validado"

# Preflight trusted da própria main, sem código de PR.
if ! EJC_ALLOW_PYTHON_MISMATCH=0 bash scripts/ci-local.sh fast >"$LOG_DIR/activation-preflight.log" 2>&1; then
  tail -n 100 "$LOG_DIR/activation-preflight.log" >&2 || true
  fail "preflight trusted da main falhou"
fi

export EJC_FALLBACK_APP_INSTALLATION_ID="$INSTALLATION_ID"
# shellcheck source=github-app-auth.sh
source scripts/github-app-auth.sh
_ejc_validate_private_key >/dev/null || fail "chave privada do App não atende política"
ejc_github_app_refresh || fail "não foi possível emitir token efêmero do App"
PRE_SHA="$(git rev-parse HEAD)"
PRE_PAYLOAD="$(jq -cn --arg sha "$PRE_SHA" '{name:"EJC Local Activation Preflight",head_sha:$sha,status:"completed",conclusion:"neutral",output:{title:"EJC Local Activation Preflight",summary:"verificação de checks:write antes da mutação da proteção"}}')"
PRE_RESULT="$(printf '%s' "$PRE_PAYLOAD" | ejc_github_app_gh_api -X POST "repos/$REPO/check-runs" -H 'Accept: application/vnd.github+json' --input - 2>/dev/null)" || fail "App sem acesso funcional à Checks API"
[ "$(printf '%s' "$PRE_RESULT" | jq -r '.app.id // -1')" = "$FALLBACK_APP_ID" ] || fail "preflight emitido por App divergente"
ejc_github_app_clear
ok "GitHub App validado"

SCHEDULER=""
if systemd_user_persistent; then SCHEDULER=systemd; elif cron_persistent; then SCHEDULER=cron; else fail "sem scheduler persistente (systemd user+linger ou cron/crond)"; fi

remove_watcher || fail "não foi possível limpar scheduler órfão"
backup_hooks_path
create_drain
HOOKS_CHANGED=0
WATCHER_INSTALLED=0
PROTECTION_CHANGED=0
rollback_enable() {
  local rc=$?
  trap - EXIT
  if [ "$rc" -ne 0 ]; then
    if [ "$PROTECTION_CHANGED" -eq 1 ] && [ -s "$PROTECTION_BACKUP" ]; then
      EJC_REPO="$REPO" EJC_BRANCH_PROTECTION_BACKUP="$PROTECTION_BACKUP" bash scripts/governanca/branch-protection.sh --restore >/dev/null 2>&1 || true
    fi
    [ "$WATCHER_INSTALLED" -eq 0 ] || remove_watcher >/dev/null 2>&1 || true
    [ "$HOOKS_CHANGED" -eq 0 ] || restore_hooks_path >/dev/null 2>&1 || true
    rm -f "$DRAIN_FILE" "$ACTIVE_FILE"
    if [ "$PROTECTION_CHANGED" -eq 1 ]; then rm -f "$PROTECTION_BACKUP"; fi
  fi
  exit "$rc"
}
trap rollback_enable EXIT

install_watcher "$SCHEDULER"
WATCHER_INSTALLED=1
scheduler_present || fail "watcher não permaneceu ativo em drain"

git config --local core.hooksPath .githooks
HOOKS_CHANGED=1

EJC_REPO="$REPO" EJC_FALLBACK_AUTHORIZATION=998 EJC_FALLBACK_APP_ID="$FALLBACK_APP_ID" EJC_BRANCH_PROTECTION_BACKUP="$PROTECTION_BACKUP" bash scripts/governanca/branch-protection.sh --fallback
PROTECTION_CHANGED=1
fallback_protection_is_active || fail "proteção fallback não foi confirmada"

write_active_state "$SCHEDULER"
rm -f "$DRAIN_FILE"
trap - EXIT
ok "fallback ativo: control plane separado do worker; GitHub Actions deixou de ser executor único"
