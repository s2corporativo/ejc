#!/usr/bin/env bash
set -euo pipefail

[ "$(id -u)" = "0" ] || { echo "Execute como root" >&2; exit 2; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET=/opt/s2-automation/host
ENV_DIR=/etc/s2-automation

install -d -m 755 "$TARGET" "$ENV_DIR"
install -m 755 "$ROOT/woodpecker-approved-sha.sh" "$TARGET/woodpecker-approved-sha.sh"

if [ ! -f "$ENV_DIR/woodpecker.env" ]; then
  install -m 600 "$ROOT/woodpecker.env.example" "$ENV_DIR/woodpecker.env"
  echo "Criado $ENV_DIR/woodpecker.env com placeholder. Configure WOODPECKER_TOKEN antes de usar o gate."
fi
chown root:root "$ENV_DIR/woodpecker.env"
chmod 600 "$ENV_DIR/woodpecker.env"

if grep -q '^WOODPECKER_TOKEN=TROCAR$' "$ENV_DIR/woodpecker.env"; then
  echo "Gate instalado, mas ainda inativo por falta do token dedicado."
  exit 0
fi

"$TARGET/woodpecker-approved-sha.sh" s2corporativo/ejc "$(git -C "$ROOT/../.." rev-parse HEAD 2>/dev/null || printf invalid)" || {
  echo "Instalacao concluida, mas a prova do SHA atual nao passou. Isso e esperado se a branch ainda nao foi integrada/validada no Woodpecker." >&2
  exit 0
}
