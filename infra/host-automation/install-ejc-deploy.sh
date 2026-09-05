#!/usr/bin/env bash
set -Eeuo pipefail

[ "$(id -u)" = "0" ] || { echo "Execute como root" >&2; exit 2; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-/opt/ejc}"
SOURCE_DIR="${EJC_SOURCE_DIR:-/opt/s2-automation/source/ejc}"
TARGET=/opt/s2-automation/host
ENV_FILE=/etc/s2-automation/woodpecker.env

[ -x "$TARGET/woodpecker-approved-sha.sh" ] || { echo "Instale primeiro o gate central com infra/host-automation/install.sh" >&2; exit 2; }
[ -f "$ENV_FILE" ] || { echo "$ENV_FILE ausente" >&2; exit 2; }
[ "$(stat -c '%u:%a' "$ENV_FILE")" = "0:600" ] || { echo "$ENV_FILE deve ser root:root 0600" >&2; exit 2; }
grep -q '^WOODPECKER_TOKEN=TROCAR$' "$ENV_FILE" && { echo "WOODPECKER_TOKEN ainda e placeholder" >&2; exit 2; }
[ -d "$SOURCE_DIR/.git" ] || {
  cat >&2 <<EOF
Checkout privado ausente em $SOURCE_DIR.
Crie previamente uma clone read-only do s2corporativo/ejc usando deploy key dedicada.
Nao coloque token ou chave privada no repositorio, no service file ou no Woodpecker.
EOF
  exit 2
}
[ -f "$APP_DIR/.env" ] || { echo "$APP_DIR/.env ausente" >&2; exit 2; }
[ "$(stat -c '%u:%a' "$APP_DIR/.env")" = "0:600" ] || { echo "$APP_DIR/.env deve ser root:root 0600" >&2; exit 2; }

git -C "$SOURCE_DIR" fetch --prune origin main
git -C "$SOURCE_DIR" rev-parse --verify origin/main >/dev/null

install -m 755 "$ROOT/ejc-deploy-approved.sh" "$TARGET/ejc-deploy-approved.sh"
install -m 644 "$ROOT/systemd/ejc-deploy-approved.service" /etc/systemd/system/ejc-deploy-approved.service
install -m 644 "$ROOT/systemd/ejc-deploy-approved.timer" /etc/systemd/system/ejc-deploy-approved.timer
systemctl daemon-reload

# Primeira prova e deploy sao executados antes de habilitar a agenda. Se o SHA
# ainda nao estiver verde no Woodpecker, nada fica automatizado pela metade.
systemctl start ejc-deploy-approved.service
systemctl enable --now ejc-deploy-approved.timer

echo "EJC deploy host-level instalado."
echo "Status: systemctl status ejc-deploy-approved.timer"
echo "Logs: journalctl -u ejc-deploy-approved.service -n 200 --no-pager"
