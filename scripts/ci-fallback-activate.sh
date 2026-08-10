#!/usr/bin/env bash
# Ativa/desativa o fallback local do EJC em uma máquina de desenvolvimento/homologação.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MODE="${1:---enable}"
REPO="${EJC_REPO:-s2corporativo/ejc}"
UNIT_DIR="${HOME}/.config/systemd/user"
UNIT="$UNIT_DIR/ejc-ci-fallback.service"
CRON_MARK='# EJC_CI_FALLBACK_998'
LOG_DIR="${HOME}/.cache/ejc-ci-fallback"
WATCHER_PATH="${EJC_FALLBACK_PATH:-$PATH}"
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
  *$'\n'*|*$'\r'*|*"'"*|*%*) fail "PATH contém caractere inseguro para scheduler autônomo" ;;
esac
case "$ROOT$LOG_DIR$REPO" in
  *$'\n'*|*$'\r'*|*"'"*|*%*|*[[:space:]]*) fail "ROOT/LOG_DIR/REPO contém caractere inseguro para scheduler autônomo" ;;
esac

remove_cron() {
  command -v crontab >/dev/null 2>&1 || return 0
  (crontab -l 2>/dev/null || true) | grep -vF "$CRON_MARK" | crontab -
}

remove_watcher() {
  if command -v systemctl >/dev/null 2>&1; then
    systemctl --user disable --now ejc-ci-fallback.service >/dev/null 2>&1 || true
    rm -f "$UNIT"
    systemctl --user daemon-reload >/dev/null 2>&1 || true
  fi
  remove_cron
}

if [ "$MODE" = "--disable" ]; then
  # Primeiro restaura a proteção cloud. Se GitHub/API estiver indisponível,
  # falha aqui e mantém o watcher ativo, evitando deixar a main esperando um
  # gate local que ninguém mais produz.
  bash scripts/governanca/branch-protection.sh --cloud
  remove_watcher
  ok "fallback desativado e branch protection restaurada para contexts do CI em nuvem"
  exit 0
fi
[ "$MODE" = "--enable" ] || fail "use --enable ou --disable"

for c in git gh jq python3 node npm psql; do command -v "$c" >/dev/null 2>&1 || fail "$c ausente"; done
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

# A ativação só pode ocorrer a partir da main limpa e exatamente sincronizada.
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

# Preferimos cron quando o daemon está comprovadamente ativo: não depende da
# sessão de login. systemd --user só é aceito com linger=yes, condição que
# garante persistência após logout/reboot sem manter uma sessão humana aberta.
SCHEDULER=""
if cron_persistente; then
  SCHEDULER=cron
elif systemd_user_persistente; then
  SCHEDULER=systemd
else
  fail "sem scheduler persistente: requer cron/crond ativo ou systemd --user com linger=yes"
fi
ok "scheduler persistente selecionado: $SCHEDULER"

# Prova mínima do executor ANTES de alterar a política da main. O gate full será
# executado por SHA de PR, mas a ativação só prossegue se o host já consegue
# executar o núcleo local sem produção, Python divergente ou sintaxe quebrada.
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

# Prepare o watcher antes de alterar branch protection. A proteção só troca
# depois que sabemos que existe um mecanismo local viável para sustentá-la.
remove_watcher
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
Environment=EJC_FALLBACK_AUTO_MERGE=1
Environment=EJC_ALLOW_PYTHON_MISMATCH=0
ExecStart=/usr/bin/env bash $ROOT/scripts/ci-fallback-watch.sh
Restart=always
RestartSec=20
StandardOutput=append:$LOG_DIR/watcher.log
StandardError=append:$LOG_DIR/watcher.log

[Install]
WantedBy=default.target
UNIT
  systemctl --user daemon-reload
fi

PROTECTION_CHANGED=0
rollback_activation() {
  local rc=$?
  trap - EXIT
  if [ "$rc" -ne 0 ] && [ "$PROTECTION_CHANGED" -eq 1 ]; then
    echo "[fallback-activate] ativação falhou; restaurando branch protection cloud…" >&2
    bash scripts/governanca/branch-protection.sh --cloud >/dev/null 2>&1 || true
  fi
  if [ "$rc" -ne 0 ]; then remove_watcher; fi
  exit "$rc"
}
trap rollback_activation EXIT

git config core.hooksPath .githooks
ok "pre-push hook local ativado"

bash scripts/governanca/branch-protection.sh --fallback
PROTECTION_CHANGED=1
ok "branch protection apontada para EJC Local Full Gate"

if [ "$SCHEDULER" = "systemd" ]; then
  systemctl --user enable --now ejc-ci-fallback.service
  systemctl --user is-enabled --quiet ejc-ci-fallback.service
  systemctl --user is-active --quiet ejc-ci-fallback.service
  ok "watcher persistente ativado via systemd --user (linger=yes)"
else
  LINE="*/5 * * * * cd '$ROOT' && /usr/bin/env PATH='$WATCHER_PATH' EJC_REPO='$REPO' EJC_FALLBACK_AUTO_MERGE=1 EJC_ALLOW_PYTHON_MISMATCH=0 bash '$ROOT/scripts/ci-fallback-watch.sh' --once >> '$LOG_DIR/watcher.log' 2>&1 $CRON_MARK"
  { crontab -l 2>/dev/null || true; echo "$LINE"; } | crontab -
  (crontab -l 2>/dev/null || true) | grep -qF "$CRON_MARK"
  ok "watcher persistente ativado via cron (5 min)"
fi

trap - EXIT
ok "fallback local autônomo ativo; GitHub Actions deixou de ser dependência de merge"
