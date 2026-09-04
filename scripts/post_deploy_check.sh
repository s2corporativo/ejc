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
  # --max-time obrigatório: sem teto, uma checagem contra backend travado
  # (TCP aceito, resposta nunca) pendura o script inteiro em vez de reprovar.
  code="$(curl -k -sS --max-time 20 -o /dev/null -w "%{http_code}" "$url" || true)"
  [ "$code" = "$expected" ] || fail "$url retornou HTTP $code; esperado $expected"
  echo "OK: $url -> $code"
}

check_container_running() {
  local container="$1"
  local running
  running="$(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || true)"
  [ "$running" = "true" ] || fail "$container ausente ou não está em execução"
  echo "OK: $container em execução"
}

echo "== EJC post-deploy check =="
echo "Dominio: ${DOMAIN}"

for container in ejc_backend ejc_db ejc_frontend ejc_worker ejc_redis; do
  check_container_running "$container"
done

check_http_code "${LOCAL_FRONTEND}/" "200"
check_http_code "${LOCAL_API}/api/health" "200"
check_http_code "${LOCAL_API}/api/health/ready" "200"
check_http_code "${BASE_URL}/" "200"
check_http_code "${BASE_URL}/api/health" "200"
check_http_code "${BASE_URL}/api/health/ready" "200"

login_code="$(curl -k -sS --max-time 20 -o /tmp/ejc_login_check.json -w "%{http_code}" \
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
