#!/usr/bin/env bash
# Ativa/desativa o fallback local do EJC em uma máquina de desenvolvimento/homologação.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MODE="${1:-}"
REPO="${EJC_REPO:-s2corporativo/ejc}"
FALLBACK_APP_ID="${EJC_FALLBACK_APP_ID:-}"
UNIT_DIR="${HOME}/.config/systemd/user"
UNIT="$UNIT_DIR/ejc-ci-fallback.service"
CRON_MARK='# EJC_CI_FALLBACK_998'
LOG_DIR="${HOME}/.cache/ejc-ci-fallback"
WATCHER_PATH="${EJC_FALLBACK_PATH:-$PATH}"
HOOKS_BACKUP="$LOG_DIR/core-hooks-path.before"
LOCK_FILE="$LOG_DIR/watcher.lock"
mkdir -p "$LOG_DIR"; chmod 700 "$LOG_DIR" 2>/dev/null || true

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

case "$WATCHER_PATH" in
  *$'\n'*|*$'\r'*|*"'"*|*'"'*|*'\'*|*%*) fail "PATH contém caractere inseguro para scheduler autônomo" ;;
esac
case "$ROOT$LOG_DIR$REPO" in
  *$'\n'*|*$'\r'*|*"'"*|*'"'*|*'\'*|*%*|*[[:space:]]*) fail "ROOT/LOG_DIR/REPO contém caractere inseguro para scheduler autônomo" ;;
esac

remove_cron() {
  command -v crontab >/dev/null 2>&1 || return 0
  local atual filtrado
  atual="$(crontab -l 2>/dev/null || true)"
  filtrado="$(printf '%s\n' "$atual" | grep -vF "$CRON_MARK" || true)"
  printf '%s\n' "$filtrado" | crontab -
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
      systemctl --user disable --now ejc-ci-fallback.service >/dev/null 2>&1 || rc=1
    fi
    if [ -e "$UNIT" ]; then
      rm -f "$UNIT" || rc=1
      systemctl --user daemon-reload >/dev/null 2>&1 || rc=1
    fi
  fi
  remove_cron || rc=1
  return "$rc"
}

restore_hooks_path() {
  if [ -f "$HOOKS_BACKUP" ]; then
    local previous
    previous="$(cat "$HOOKS_BACKUP")"
    if [ "$previous" = "__UNSET__" ]; then
      git config --local --unset-all core.hooksPath >/dev/null 2>&1 || true
    else
      git config --local core.hooksPath "$previous"
    fi
    rm -f "$HOOKS_BACKUP"
  fi
}

if [ "$MODE" = "--disable" ]; then
  remove_watcher || fail "não foi possível remover o watcher; proteção fallback mantida"
  bash scripts/governanca/branch-protection.sh --cloud
  restore_hooks_path
  ok "fallback desativado e branch protection restaurada para contexts do CI em nuvem"
  exit 0
fi
[ "$MODE" = "--enable" ] || fail "uso: $0 --enable | --disable"

[[ "$FALLBACK_APP_ID" =~ ^[1-9][0-9]*$ ]] \
  || fail "EJC_FALLBACK_APP_ID numérico (>0) do GitHub App dedicado é obrigatório"
for c in git gh jq python3 node npm psql flock; do command -v "$c" >/dev/null 2>&1 || fail "$c ausente"; done
command -v docker >/dev/null 2>&1 || fail "Docker ausente (fallback promovível exige banco efêmero isolado)"
docker info >/dev/null 2>&1 || fail "Docker não acessível pelo usuário atual"
if docker ps --format '{{.Names}}' 2>/dev/null | grep -Eq '^(ejc_backend|ejc_worker|ejc_db|ejc_frontend|ejc_redis)$'; then
  fail "containers canônicos do EJC ativos; host não é elegível para CI de PR"
fi
gh auth status >/dev/null 2>&1 || fail "gh não autenticado neste host"

PYVER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [ "$PYVER" != "3.11" ] && ! command -v python3.11 >/dev/null 2>&1; then fail "Python 3.11 ausente"; fi
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
[ "$NODE_MAJOR" = "22" ] || fail "Node 22 requerido; encontrado $(node --version)"

[ "$(git branch --show-current)" = "main" ] || fail "ative somente a partir da branch main"
[ -z "$(git status --porcelain)" ] || fail "checkout local possui alterações; limpe-o antes da ativação"
git fetch --quiet origin main || fail "não foi possível atualizar origin/main"
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || fail "main local não corresponde à origin/main"

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
  scripts/governanca/ci-local-governanca.sh \
  scripts/governanca/branch-protection.sh; do
  bash -n "$script" || fail "sintaxe inválida em $script"
done
ok "sintaxe dos componentes do fallback"

log_preflight="$LOG_DIR/activation-preflight.log"
if ! EJC_ALLOW_PYTHON_MISMATCH=0 bash scripts/ci-local.sh fast >"$log_preflight" 2>&1; then
  tail -n 100 "$log_preflight" >&2 || true
  fail "preflight local falhou; branch protection não foi alterada"
fi
ok "preflight local aprovado antes da alteração da branch protection"

remove_watcher || fail "não foi possível limpar watcher anterior"
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
Environment=EJC_REPO=$REPO
Environment=EJC_FALLBACK_APP_ID=$FALLBACK_APP_ID
Environment=EJC_FALLBACK_AUTO_MERGE=1
Environment=EJC_ALLOW_PYTHON_MISMATCH=0
ExecStart=/usr/bin/flock -n $LOCK_FILE /usr/bin/env bash $ROOT/scripts/ci-fallback-watch.sh
Restart=on-failure
RestartSec=20
StandardOutput=append:$LOG_DIR/watcher.log
StandardError=append:$LOG_DIR/watcher.log

[Install]
WantedBy=default.target
UNIT
  systemctl --user daemon-reload
fi

PROTECTION_CHANGED=0
HOOKS_CHANGED=0
rollback_activation() {
  local rc=$?
  trap - EXIT
  if [ "$rc" -ne 0 ]; then
    remove_watcher >/dev/null 2>&1 || true
    if [ "$PROTECTION_CHANGED" -eq 1 ]; then
      echo "[fallback-activate] ativação falhou; restaurando branch protection cloud…" >&2
      bash scripts/governanca/branch-protection.sh --cloud >/dev/null 2>&1 || true
    fi
    if [ "$HOOKS_CHANGED" -eq 1 ]; then restore_hooks_path >/dev/null 2>&1 || true; fi
  fi
  exit "$rc"
}
trap rollback_activation EXIT

# Leia apenas o escopo local. Um valor global de core.hooksPath não deve ser
# materializado dentro do repositório durante ativação/desativação.
if git config --local --get core.hooksPath >/dev/null 2>&1; then
  git config --local --get core.hooksPath > "$HOOKS_BACKUP"
else
  printf '%s\n' '__UNSET__' > "$HOOKS_BACKUP"
fi
chmod 600 "$HOOKS_BACKUP" 2>/dev/null || true
git config --local core.hooksPath .githooks
HOOKS_CHANGED=1
ok "pre-push hook local ativado"

# O script de proteção pode aplicar o PUT antes de sua validação final; marque
# a mutação como potencial antes da chamada para garantir rollback fail-closed.
PROTECTION_CHANGED=1
EJC_FALLBACK_AUTHORIZATION=998 EJC_FALLBACK_APP_ID="$FALLBACK_APP_ID" \
  bash scripts/governanca/branch-protection.sh --fallback
ok "branch protection apontada para EJC Local Full Gate vinculado ao GitHub App id=$FALLBACK_APP_ID"

if [ "$SCHEDULER" = "systemd" ]; then
  systemctl --user enable --now ejc-ci-fallback.service
  systemctl --user is-enabled --quiet ejc-ci-fallback.service
  systemctl --user is-active --quiet ejc-ci-fallback.service
  ok "watcher persistente ativado via systemd --user (linger=yes)"
else
  LINE="*/5 * * * * cd '$ROOT' && /usr/bin/env PATH='$WATCHER_PATH' EJC_REPO='$REPO' EJC_FALLBACK_APP_ID='$FALLBACK_APP_ID' EJC_FALLBACK_AUTO_MERGE=1 EJC_ALLOW_PYTHON_MISMATCH=0 flock -n '$LOCK_FILE' bash '$ROOT/scripts/ci-fallback-watch.sh' --once >> '$LOG_DIR/watcher.log' 2>&1 $CRON_MARK"
  { crontab -l 2>/dev/null || true; echo "$LINE"; } | crontab -
  (crontab -l 2>/dev/null || true) | grep -qF "$CRON_MARK"
  ok "watcher persistente ativado via cron (5 min, lock exclusivo)"
fi

trap - EXIT
ok "fallback local autônomo ativo; GitHub Actions deixou de ser dependência de merge"
