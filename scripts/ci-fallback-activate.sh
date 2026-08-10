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
mkdir -p "$LOG_DIR"; chmod 700 "$LOG_DIR" 2>/dev/null || true

fail(){ echo "[fallback-activate] ERRO: $*" >&2; exit 1; }
ok(){ echo "[fallback-activate] ok: $*"; }

case "$(realpath "$ROOT" 2>/dev/null || printf '%s' "$ROOT")" in
  /opt/ejc|/opt/ejc/*) fail "recusado em /opt/ejc (produção)" ;;
esac
[ "$(id -u)" -ne 0 ] || fail "não execute como root"

remove_cron() {
  command -v crontab >/dev/null 2>&1 || return 0
  (crontab -l 2>/dev/null || true) | grep -vF "$CRON_MARK" | crontab -
}

if [ "$MODE" = "--disable" ]; then
  if command -v systemctl >/dev/null 2>&1; then
    systemctl --user disable --now ejc-ci-fallback.service >/dev/null 2>&1 || true
    rm -f "$UNIT"
    systemctl --user daemon-reload >/dev/null 2>&1 || true
  fi
  remove_cron
  bash scripts/governanca/branch-protection.sh --cloud
  ok "fallback desativado e branch protection restaurada para contexts do CI em nuvem"
  exit 0
fi
[ "$MODE" = "--enable" ] || fail "use --enable ou --disable"

for c in git gh jq python3 node npm psql; do command -v "$c" >/dev/null 2>&1 || fail "$c ausente"; done
command -v docker >/dev/null 2>&1 || fail "Docker ausente (fallback promovível exige banco efêmero isolado)"
docker info >/dev/null 2>&1 || fail "Docker não acessível pelo usuário atual"
gh auth status >/dev/null 2>&1 || fail "gh não autenticado neste host"

PYVER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [ "$PYVER" != "3.11" ] && ! command -v python3.11 >/dev/null 2>&1; then fail "Python 3.11 ausente"; fi
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
[ "$NODE_MAJOR" = "22" ] || fail "Node 22 requerido; encontrado $(node --version)"

git config core.hooksPath .githooks
ok "pre-push hook local ativado"

bash scripts/governanca/branch-protection.sh --fallback
ok "branch protection apontada para EJC Local Full Gate"

remove_cron
if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
  mkdir -p "$UNIT_DIR"
  cat > "$UNIT" <<UNIT
[Unit]
Description=EJC CI fallback watcher (worktree isolado)
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
Environment=EJC_REPO=$REPO
Environment=EJC_FALLBACK_AUTO_MERGE=1
ExecStart=$ROOT/scripts/ci-fallback-watch.sh
Restart=always
RestartSec=20
StandardOutput=append:$LOG_DIR/watcher.log
StandardError=append:$LOG_DIR/watcher.log

[Install]
WantedBy=default.target
UNIT
  systemctl --user daemon-reload
  systemctl --user enable --now ejc-ci-fallback.service
  ok "watcher ativado via systemd --user"
elif command -v crontab >/dev/null 2>&1; then
  LINE="*/5 * * * * cd '$ROOT' && EJC_REPO='$REPO' EJC_FALLBACK_AUTO_MERGE=1 '$ROOT/scripts/ci-fallback-watch.sh' --once >> '$LOG_DIR/watcher.log' 2>&1 $CRON_MARK"
  { crontab -l 2>/dev/null || true; echo "$LINE"; } | crontab -
  ok "watcher ativado via crontab (5 min)"
else
  fail "sem systemd --user e sem crontab; não há scheduler local seguro disponível"
fi

ok "fallback local autônomo ativo; GitHub Actions deixou de ser dependência de merge"
