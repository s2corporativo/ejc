#!/usr/bin/env bash
set -euo pipefail

[ "$(id -u)" = "0" ] || { echo "Execute como root" >&2; exit 2; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${EJC_HOST_AUTOMATION_TARGET:-/opt/s2-automation/host}"
ENV_DIR="${EJC_HOST_AUTOMATION_ENV_DIR:-/etc/s2-automation}"
ENV_FILE="$ENV_DIR/woodpecker.env"
LOCAL_DB_DEFAULT="${WOODPECKER_LOCAL_DB_DEFAULT:-/var/lib/docker/volumes/woodpecker_woodpecker-server-data/_data/woodpecker.sqlite}"

install -d -m 755 "$TARGET" "$ENV_DIR"
install -m 755 "$ROOT/woodpecker-approved-sha.sh" "$TARGET/woodpecker-approved-sha.sh"

if [ ! -f "$ENV_FILE" ]; then
  install -m 600 "$ROOT/woodpecker.env.example" "$ENV_FILE"
  echo "Criado $ENV_FILE."
fi
chown root:root "$ENV_FILE"
chmod 600 "$ENV_FILE"

# Na instalação self-hosted canônica, prefira consultar o SQLite local em modo
# read-only. Isso evita criar um novo segredo apenas para o gate de deploy.
if [ -f "$LOCAL_DB_DEFAULT" ]; then
  if grep -q '^WOODPECKER_LOCAL_DB=' "$ENV_FILE"; then
    # Preserva caminho explicitamente configurado; só preenche chave vazia.
    if grep -q '^WOODPECKER_LOCAL_DB=$' "$ENV_FILE"; then
      sed -i "s#^WOODPECKER_LOCAL_DB=$#WOODPECKER_LOCAL_DB=$LOCAL_DB_DEFAULT#" "$ENV_FILE"
      echo "Gate configurado para SQLite local read-only."
    fi
  else
    # Upgrade de instalações antigas: o arquivo legado pode não conhecer a
    # variável. Acrescenta o modo local canônico sem depender de token novo.
    printf '
WOODPECKER_LOCAL_DB=%s
' "$LOCAL_DB_DEFAULT" >> "$ENV_FILE"
    echo "Gate legado migrado para SQLite local read-only."
  fi
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if [ -z "${WOODPECKER_LOCAL_DB:-}" ]; then
  if [ -z "${WOODPECKER_TOKEN:-}" ] || [ "${WOODPECKER_TOKEN:-}" = "TROCAR" ]; then
    echo "Gate instalado, mas inativo: configure WOODPECKER_LOCAL_DB ou um token dedicado." >&2
    exit 0
  fi
fi

WOODPECKER_HOST_ENV_FILE="$ENV_FILE" \
  "$TARGET/woodpecker-approved-sha.sh" s2corporativo/ejc \
  "$(git -C "$ROOT/../.." rev-parse HEAD 2>/dev/null || printf invalid)" || {
  echo "Instalacao concluida, mas a prova do SHA atual nao passou. Isso e esperado se a branch ainda nao foi integrada/validada no Woodpecker." >&2
  exit 0
}
