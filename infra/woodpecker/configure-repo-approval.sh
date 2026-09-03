#!/usr/bin/env bash
set -euo pipefail

# Aplica no repositório já habilitado o mesmo modo de aprovação versionado no
# Compose. O token é obrigatório apenas no ambiente do operador e nunca é
# gravado, impresso ou versionado.
API_BASE="${WOODPECKER_API_BASE:-https://ci.depaulateixeira.adv.br/api}"
REPO_ID="${WOODPECKER_REPO_ID:-2}"

: "${WOODPECKER_TOKEN:?defina WOODPECKER_TOKEN somente no ambiente da sessão}"

response_file="$(mktemp)"
trap 'rm -f "${response_file}"' EXIT

http_code="$({
  curl --silent --show-error \
    --output "${response_file}" \
    --write-out '%{http_code}' \
    --request PATCH \
    --header "Authorization: Bearer ${WOODPECKER_TOKEN}" \
    --header 'Content-Type: application/json' \
    --data '{"require_approval":"forks"}' \
    "${API_BASE}/repos/${REPO_ID}"
} 2>&1)"

if [[ "${http_code}" != "200" ]]; then
  echo "Falha ao atualizar o modo de aprovação do Woodpecker (HTTP ${http_code})." >&2
  exit 1
fi

if ! grep -Eq '"require_approval"[[:space:]]*:[[:space:]]*"forks"' "${response_file}"; then
  echo "A API respondeu 200, mas não confirmou require_approval=forks." >&2
  exit 1
fi

echo "Woodpecker repo ${REPO_ID}: require_approval=forks confirmado."
