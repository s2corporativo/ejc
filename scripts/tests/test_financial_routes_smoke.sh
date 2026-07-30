#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="${ROOT}/scripts/smoke_rotas_financeiras.sh"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

MOCK_CURL="${TMP_DIR}/curl"
cat >"$MOCK_CURL" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail

output=""
url=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --output)
      output="$2"
      shift 2
      ;;
    --write-out|--connect-timeout|--max-time)
      shift 2
      ;;
    --config)
      [ "$2" = "-" ] || exit 90
      config="$(cat)"
      [[ "$config" == *'Authorization: Bearer '* ]] || exit 91
      shift 2
      ;;
    --silent|--show-error|--location)
      shift
      ;;
    *)
      url="$1"
      shift
      ;;
  esac
done

printf '%s\n' "$url" >>"${MOCK_LOG:?}"

if [[ "$url" == */api/health ]]; then
  printf '{"commit":"%s"}' "${MOCK_DEPLOYED_SHA:-abcdef1234567890}" >"$output"
  printf '%s' "${MOCK_HEALTH_CODE:-200}"
  exit 0
fi

code=200
if [ "${MOCK_FAIL_ROUTE:-}" = "$url" ]; then
  code="${MOCK_FAIL_CODE:-500}"
fi
printf '%s' "$code"
MOCK
chmod +x "$MOCK_CURL"

run_smoke() {
  local output_file="$1"
  shift
  env \
    CURL_BIN="$MOCK_CURL" \
    MOCK_LOG="${TMP_DIR}/requests.log" \
    EJC_BASE_URL="https://homolog.example.test" \
    EJC_EXPECTED_SHA="abcdef1" \
    EJC_SMOKE_TOKEN="token-ultrassecreto" \
    "$@" \
    bash "$SCRIPT" >"$output_file" 2>&1
}

: >"${TMP_DIR}/requests.log"
run_smoke "${TMP_DIR}/success.log"
grep -q "smoke das rotas financeiras concluído" "${TMP_DIR}/success.log"
! grep -q "token-ultrassecreto" "${TMP_DIR}/success.log"
grep -qx "https://homolog.example.test/api/v1/despesas" "${TMP_DIR}/requests.log"
grep -qx "https://homolog.example.test/api/v1/office-contracts" "${TMP_DIR}/requests.log"
grep -qx "https://homolog.example.test/api/v1/partner-withdrawals" "${TMP_DIR}/requests.log"

if env \
  CURL_BIN="$MOCK_CURL" \
  MOCK_LOG="${TMP_DIR}/missing-token.log" \
  EJC_BASE_URL="https://homolog.example.test" \
  EJC_EXPECTED_SHA="abcdef1" \
  bash "$SCRIPT" >"${TMP_DIR}/missing-token.out" 2>&1; then
  echo "esperava falha sem token" >&2
  exit 1
fi
grep -q "EJC_SMOKE_TOKEN é obrigatório" "${TMP_DIR}/missing-token.out"

if run_smoke "${TMP_DIR}/sha-mismatch.log" MOCK_DEPLOYED_SHA="9999999999999999"; then
  echo "esperava falha para SHA divergente" >&2
  exit 1
fi
grep -q "SHA implantado" "${TMP_DIR}/sha-mismatch.log"
grep -q "diverge do esperado" "${TMP_DIR}/sha-mismatch.log"

failed_url="https://homolog.example.test/api/v1/office-contracts"
if run_smoke \
  "${TMP_DIR}/route-404.log" \
  MOCK_FAIL_ROUTE="$failed_url" \
  MOCK_FAIL_CODE="404"; then
  echo "esperava falha para rota 404" >&2
  exit 1
fi
grep -q "/api/v1/office-contracts -> 404" "${TMP_DIR}/route-404.log"

if run_smoke \
  "${TMP_DIR}/route-403.log" \
  MOCK_FAIL_ROUTE="$failed_url" \
  MOCK_FAIL_CODE="403"; then
  echo "esperava falha para perfil sem permissão" >&2
  exit 1
fi
grep -q "/api/v1/office-contracts -> 403" "${TMP_DIR}/route-403.log"

echo "OK: testes do smoke de rotas financeiras"
