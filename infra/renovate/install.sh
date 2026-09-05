#!/usr/bin/env bash
set -euo pipefail

[ "$(id -u)" = "0" ] || { echo "Execute como root" >&2; exit 2; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET=/opt/s2-automation/renovate
ENV_DIR=/etc/s2-automation

install -d -m 755 "$TARGET" "$ENV_DIR"
install -m 644 "$ROOT/config.js" "$TARGET/config.js"
install -m 755 "$ROOT/run.sh" "$TARGET/run.sh"
install -m 644 "$ROOT/systemd/s2-renovate.service" /etc/systemd/system/s2-renovate.service
install -m 644 "$ROOT/systemd/s2-renovate.timer" /etc/systemd/system/s2-renovate.timer

if [ ! -f "$ENV_DIR/renovate.env" ]; then
  install -m 600 "$ROOT/renovate.env.example" "$ENV_DIR/renovate.env"
  echo "Credencial criada como placeholder em $ENV_DIR/renovate.env. Preencha RENOVATE_TOKEN antes de habilitar o timer."
fi
chown root:root "$ENV_DIR/renovate.env"
chmod 600 "$ENV_DIR/renovate.env"

systemctl daemon-reload

if grep -q '^RENOVATE_TOKEN=TROCAR$' "$ENV_DIR/renovate.env"; then
  echo "Timer NAO habilitado: configure RENOVATE_TOKEN e rode:"
  echo "  systemctl start s2-renovate.service"
  echo "  systemctl enable --now s2-renovate.timer"
  exit 0
fi

systemctl start s2-renovate.service
systemctl enable --now s2-renovate.timer
