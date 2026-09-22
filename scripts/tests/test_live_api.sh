#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
MAX_WAIT="${MAX_WAIT:-90}"

fail() {
  printf '[live-api][endpoint_failure] %s\n' "$*" >&2
  exit 1
}

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
  if [ "$code" != "$expected" ]; then
    printf '[live-api] resposta de %s: ' "$url" >&2
    cat /tmp/ejc-live-response.json >&2 2>/dev/null || true
    printf '\n' >&2
    fail "$url retornou $code; esperado $expected"
  fi
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

# Rotas críticas precisam existir. Sem autenticação podem negar ou rejeitar o
# método/payload, mas 404 é regressão de registro e deve falhar fechado.
for path in /api/cases /api/documents /api/rag/buscar; do
  code="$(curl -sS --max-time 10 -o /tmp/ejc-live-critical.json -w '%{http_code}' "$BASE_URL$path" || true)"
  case "$code" in
    401|403|405|422) printf '[live-api] OK %s -> %s (gate/contrato)\n' "$path" "$code" ;;
    *) fail "$path retornou $code; esperado 401, 403, 405 ou 422; 404/5xx são falha" ;;
  esac
done
