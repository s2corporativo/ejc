#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${EJC_DOMAIN:-ejc.depaulateixeira.adv.br}"
BASE_URL="https://${DOMAIN}"
LOCAL_FRONTEND="http://127.0.0.1:8080"
LOCAL_API="http://127.0.0.1:8000"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

check_http_code() {
  local url="$1"
  local expected="$2"
  local code
  code="$(curl -k -sS -o /dev/null -w "%{http_code}" "$url" || true)"
  [ "$code" = "$expected" ] || fail "$url retornou HTTP $code; esperado $expected"
  echo "OK: $url -> $code"
}

echo "== EJC post-deploy check =="
echo "Dominio: ${DOMAIN}"

docker ps --format '{{.Names}} {{.Status}}' | grep -E '^ejc_(backend|db|frontend) ' || fail "containers EJC ausentes"

check_http_code "${LOCAL_FRONTEND}/" "200"
check_http_code "${LOCAL_API}/api/health" "200"
check_http_code "${BASE_URL}/" "200"
check_http_code "${BASE_URL}/api/health" "200"

login_code="$(curl -k -sS -o /tmp/ejc_login_check.json -w "%{http_code}" \
  -H "Content-Type: application/json" \
  -d '{"email":"healthcheck@invalid.local","password":"invalid"}' \
  "${BASE_URL}/api/auth/login" || true)"

case "$login_code" in
  401|422|429) echo "OK: endpoint de login respondeu HTTP ${login_code}" ;;
  *) fail "endpoint de login retornou HTTP ${login_code}" ;;
esac

docker exec ejc_backend python -m py_compile \
  /app/app/services/document_format.py \
  /app/app/services/documental.py \
  /app/app/services/peca_service.py \
  /app/app/services/pdf_service.py \
  /app/app/routers/legal_docs.py
echo "OK: modulos Python criticos compilam"

echo "== OK: post-deploy check concluido =="
