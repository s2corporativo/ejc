#!/usr/bin/env bash
set -euo pipefail

# Aplica no repositório já habilitado o mesmo modo de aprovação versionado no
# Compose. O PAT existe apenas em memória durante esta execução: não é gravado,
# impresso nem passado como argumento do processo curl.
API_BASE="${WOODPECKER_API_BASE:-https://ci.depaulateixeira.adv.br/api}"
REPO_ID="${WOODPECKER_REPO_ID:-2}"

if [[ -z "${WOODPECKER_TOKEN:-}" ]]; then
  read -r -s -p "Woodpecker PAT: " WOODPECKER_TOKEN
  echo
fi

if [[ -z "${WOODPECKER_TOKEN}" ]]; then
  echo "PAT do Woodpecker não informado." >&2
  exit 1
fi

response_file="$(mktemp)"
trap 'rm -f "${response_file}"' EXIT

# O header de autorização entra no curl pela configuração em stdin. Assim o
# token não aparece em argv/process list nem precisa de arquivo temporário.
if ! http_code="$(
  printf 'header = "Authorization: Bearer %s"\n' "${WOODPECKER_TOKEN}" |
    curl --config - \
      --silent --show-error \
      --output "${response_file}" \
      --write-out '%{http_code}' \
      --request PATCH \
      --header 'Content-Type: application/json' \
      --data '{"require_approval":"forks"}' \
      "${API_BASE}/repos/${REPO_ID}"
)"; then
  unset WOODPECKER_TOKEN
  echo "Falha de transporte ao chamar a API do Woodpecker." >&2
  exit 1
fi

unset WOODPECKER_TOKEN

if [[ "${http_code}" != "200" ]]; then
  echo "Falha ao atualizar o modo de aprovação do Woodpecker (HTTP ${http_code})." >&2
  exit 1
fi

if ! grep -Eq '"require_approval"[[:space:]]*:[[:space:]]*"forks"' "${response_file}"; then
  echo "A API respondeu 200, mas não confirmou require_approval=forks." >&2
  exit 1
fi

echo "Woodpecker repo ${REPO_ID}: require_approval=forks confirmado."
