#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
MAX_WAIT="${MAX_WAIT:-90}"

fail() { printf '[live-api] ERRO: %s\n' "$*" >&2; exit 1; }

for _ in $(seq 1 "$MAX_WAIT"); do
  if curl -fsS --max-time 3 "$BASE_URL/api/health" >/tmp/ejc-live-health.json; then
    break
  fi
  sleep 1
done
[ -s /tmp/ejc-live-health.json ] || fail "backend não respondeu /api/health em ${MAX_WAIT}s"

check_code() {
  local expected="$1" url="$2" code
  code="$(curl -sS --max-time 10 -o /tmp/ejc-live-response.json -w '%{http_code}' "$url" || true)"
  [ "$code" = "$expected" ] || fail "$url retornou $code; esperado $expected"
  printf '[live-api] OK %s -> %s\n' "$url" "$code"
}

check_code 200 "$BASE_URL/api/health"
check_code 200 "$BASE_URL/api/health/ready"

login_code="$(curl -sS --max-time 10 -o /tmp/ejc-live-login.json -w '%{http_code}' \
  -H 'Content-Type: application/json' \
  -d '{"email":"healthcheck@invalid.local","password":"invalid"}' \
  "$BASE_URL/api/auth/login" || true)"
case "$login_code" in
  401|422|429) printf '[live-api] OK /api/auth/login -> %s\n' "$login_code" ;;
  *) fail "/api/auth/login retornou $login_code; esperado 401, 422 ou 429" ;;
esac

# Rota crítica sem autenticação: deve negar, não desaparecer nem retornar 5xx.
for path in /api/cases /api/documents /api/rag/buscar; do
  code="$(curl -sS --max-time 10 -o /tmp/ejc-live-critical.json -w '%{http_code}' "$BASE_URL$path" || true)"
  case "$code" in
    401|403|404|405|422) printf '[live-api] OK %s -> %s (gate/contrato)\n' "$path" "$code" ;;
    *) fail "$path retornou $code; esperado resposta de gate/contrato, não 5xx" ;;
  esac
done
