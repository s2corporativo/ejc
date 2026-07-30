#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${EJC_BASE_URL:-https://ejc.depaulateixeira.adv.br}"
EXPECTED_SHA="${EJC_EXPECTED_SHA:-}"
SMOKE_TOKEN="${EJC_SMOKE_TOKEN:-}"
CURL_BIN="${CURL_BIN:-curl}"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

case "$BASE_URL" in
  http://*|https://*) ;;
  *) fail "EJC_BASE_URL deve começar com http:// ou https://" ;;
esac
BASE_URL="${BASE_URL%/}"

[[ "$EXPECTED_SHA" =~ ^[0-9a-fA-F]{7,40}$ ]] ||
  fail "EJC_EXPECTED_SHA deve conter de 7 a 40 caracteres hexadecimais"

[ -n "$SMOKE_TOKEN" ] ||
  fail "EJC_SMOKE_TOKEN é obrigatório e deve ser fornecido apenas para esta execução"

unset EJC_SMOKE_TOKEN

health_file="$(mktemp)"
trap 'rm -f "$health_file"' EXIT

health_code="$(
  "$CURL_BIN" \
    --silent \
    --show-error \
    --location \
    --connect-timeout 10 \
    --max-time 30 \
    --output "$health_file" \
    --write-out "%{http_code}" \
    "${BASE_URL}/api/health" || true
)"
[ "$health_code" = "200" ] ||
  fail "${BASE_URL}/api/health retornou HTTP ${health_code}; esperado 200"

deployed_sha="$(
  python3 - "$health_file" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    payload = json.load(stream)
print(str(payload.get("commit") or ""))
PY
)" || fail "resposta de /api/health não contém JSON válido"

[[ "$deployed_sha" =~ ^[0-9a-fA-F]{7,40}$ ]] ||
  fail "/api/health não informou um SHA de commit válido"

expected_lower="${EXPECTED_SHA,,}"
deployed_lower="${deployed_sha,,}"
if [[ "$expected_lower" != "$deployed_lower"* && "$deployed_lower" != "$expected_lower"* ]]; then
  fail "SHA implantado (${deployed_sha}) diverge do esperado (${EXPECTED_SHA})"
fi
echo "OK: SHA implantado confere (${deployed_sha})"

check_financial_route() {
  local route="$1"
  local url="${BASE_URL}${route}"
  local code

  code="$(
    printf 'header = "Authorization: Bearer %s"\n' "$SMOKE_TOKEN" |
      "$CURL_BIN" \
        --config - \
        --silent \
        --show-error \
        --location \
        --connect-timeout 10 \
        --max-time 30 \
        --output /dev/null \
        --write-out "%{http_code}" \
        "$url" || true
  )"

  case "$code" in
    200) echo "OK: ${route} -> 200" ;;
    401) fail "${route} -> 401; token ausente, inválido ou expirado" ;;
    403) fail "${route} -> 403; perfil sem permissão financeira" ;;
    404) fail "${route} -> 404; rota não alcançou o runtime implantado" ;;
    000|"") fail "${route} -> falha de transporte" ;;
    *) fail "${route} -> HTTP ${code}; esperado 200" ;;
  esac
}

check_financial_route "/api/v1/despesas"
check_financial_route "/api/v1/office-contracts"
check_financial_route "/api/v1/partner-withdrawals"

echo "OK: smoke das rotas financeiras concluído"
