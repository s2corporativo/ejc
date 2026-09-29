#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/ejc}"
SYSTEMD_DIR="/etc/systemd/system"

fail() { printf '[ejc-observability] ERRO: %s\n' "$*" >&2; exit 2; }

[ "$(id -u)" -eq 0 ] || fail "execute como root"
[ -f "$APP_DIR/scripts/release_evidence.py" ] || fail "release_evidence.py ausente"
[ -f "$APP_DIR/infra/systemd/ejc-observability-snapshot.service" ] || fail "unit service ausente"
[ -f "$APP_DIR/infra/systemd/ejc-observability-snapshot.timer" ] || fail "unit timer ausente"

install -m 0644   "$APP_DIR/infra/systemd/ejc-observability-snapshot.service"   "$SYSTEMD_DIR/ejc-observability-snapshot.service"
install -m 0644   "$APP_DIR/infra/systemd/ejc-observability-snapshot.timer"   "$SYSTEMD_DIR/ejc-observability-snapshot.timer"

systemctl daemon-reload
systemctl enable --now ejc-observability-snapshot.timer
systemctl start ejc-observability-snapshot.service
systemctl is-active --quiet ejc-observability-snapshot.timer
printf '[ejc-observability] timer ativo e primeira evidência coletada\n'
