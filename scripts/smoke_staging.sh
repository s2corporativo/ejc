#!/usr/bin/env bash
# Gates automatizados de staging — governança v3 (fluxo autônomo).
#
# Roda contra a stack de staging (projeto ejc-staging, portas 8001/8081) após
# cada deploy de staging: health-check, frontend, autenticação, banco/migrations
# e, quando RUN_STAGING_PYTEST=1, a suíte pytest completa dentro do container.
# Qualquer falha reprova o gate e impede a promoção automática para produção.
set -euo pipefail

API="http://127.0.0.1:8001"
FRONT="http://127.0.0.1:8081"

fail() { echo "FAIL: $1" >&2; exit 1; }
ok() { echo "OK: $1"; }

echo "== EJC staging smoke =="

# Containers de staging de pé
for c in ejc_stg_db ejc_stg_backend ejc_stg_frontend; do
  docker ps --format '{{.Names}}' | grep -qx "$c" || fail "container $c ausente"
done
ok "containers de staging ativos"

# Health-check com espera de subida (até 2 min)
for _ in $(seq 1 24); do
  curl -fsS "$API/api/health" >/dev/null 2>&1 && break
  sleep 5
done
curl -fsS "$API/api/health" >/dev/null || fail "$API/api/health indisponível"
ok "health-check da API"

code="$(curl -sS -o /dev/null -w '%{http_code}' "$FRONT/")"
[ "$code" = "200" ] || fail "frontend staging retornou HTTP $code"
ok "frontend responde 200"

# Autenticação: credencial inválida deve ser rejeitada, nunca 5xx
login_code="$(curl -sS -o /dev/null -w '%{http_code}' \
  -H 'Content-Type: application/json' \
  -d '{"email":"smoke@invalid.local","password":"invalid"}' \
  "$API/api/auth/login" || true)"
case "$login_code" in
  401|422|429) ok "endpoint de login rejeita credencial inválida ($login_code)" ;;
  *) fail "endpoint de login retornou HTTP $login_code" ;;
esac

# Banco: head único de migration aplicado
revs="$(docker exec ejc_stg_db sh -lc \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atq -c "SELECT count(*) FROM alembic_version"')"
[ "$(printf '%s' "$revs" | tr -d '[:space:]')" = "1" ] \
  || fail "alembic_version deveria ter exatamente 1 revisão (encontrado: $revs)"
ok "migrations aplicadas com head único"

# Suíte de testes completa dentro do container (backend + auth + rotas + IA/RAG
# conforme marcadores do próprio repositório). Opt-in por custo de tempo.
if [ "${RUN_STAGING_PYTEST:-0}" = "1" ]; then
  docker exec ejc_stg_backend sh -lc 'cd /app && python -m pytest tests -x -q' \
    || fail "pytest reprovou em staging"
  ok "suíte pytest verde em staging"
fi

echo "== OK: gates de staging aprovados =="
