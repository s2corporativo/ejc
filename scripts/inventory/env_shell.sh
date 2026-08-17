#!/bin/bash
# Carrega o .env do repositório (respeitando comentários e valores com espaços)
# e executa os argumentos recebidos com o ambiente carregado.
set -e
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$REPO/.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "ERRO: $ENV_FILE não existe" >&2
  exit 1
fi
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in
    \#*|"") continue ;;
    *=*)
      key="${line%%=*}"
      value="${line#*=}"
      # Remove aspas externas se presentes
      value="$(echo "$value" | sed -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'$/\1/")"
      export "$key=$value"
      ;;
  esac
done < "$ENV_FILE"
exec "$@"
