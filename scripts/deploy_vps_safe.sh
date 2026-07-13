#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/ejc}"
DOMAIN="${EJC_DOMAIN:-ejc.depaulateixeira.adv.br}"
RUN_MIGRATIONS="${RUN_MIGRATIONS:-0}"
RUN_SEEDS="${RUN_SEEDS:-0}"

cd "$APP_DIR"

timestamp() { date +"%Y%m%d_%H%M%S"; }
log() { echo "[$(date '+%F %T')] $*"; }

rollback() {
  log "Deploy falhou. Iniciando rollback seguro."
  if [ -n "${OLD_BACKEND_IMAGE:-}" ]; then
    docker tag "$OLD_BACKEND_IMAGE" ejc-backend:latest || true
  fi
  if [ -n "${OLD_FRONTEND_IMAGE:-}" ]; then
    docker tag "$OLD_FRONTEND_IMAGE" ejc-frontend:latest || true
  fi
  docker compose up -d --no-deps backend frontend || true
  sleep 8
  bash "$APP_DIR/scripts/post_deploy_check.sh" || true
  exit 1
}

trap rollback ERR

log "EJC deploy seguro iniciado para ${DOMAIN}"

[ -f .env ] || { echo "Arquivo .env ausente em ${APP_DIR}" >&2; exit 1; }
docker compose config >/tmp/ejc_compose_config_$(timestamp).txt

OLD_BACKEND_IMAGE="$(docker inspect -f '{{.Image}}' ejc_backend 2>/dev/null || true)"
OLD_FRONTEND_IMAGE="$(docker inspect -f '{{.Image}}' ejc_frontend 2>/dev/null || true)"
log "Imagem backend anterior: ${OLD_BACKEND_IMAGE:-indisponivel}"
log "Imagem frontend anterior: ${OLD_FRONTEND_IMAGE:-indisponivel}"

log "Backup antes do deploy"
bash scripts/backup.sh

log "Build backend e frontend"
docker compose build backend frontend

log "Subindo backend"
docker compose up -d --no-deps backend
# Boot frio pós-build leva mais que 10s: espera até 60s (12 x 5s) antes de
# declarar falha — o teto curto gerava rollback falso-negativo com o deploy
# na prática saudável.
backend_ok=0
for _ in $(seq 1 12); do
  sleep 5
  if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    backend_ok=1
    break
  fi
done
[ "$backend_ok" = "1" ] || { log "Backend não respondeu em 60s"; exit 1; }

if [ "$RUN_MIGRATIONS" = "1" ]; then
  log "RUN_MIGRATIONS=1: aplicando Alembic"
  docker compose exec -T backend alembic upgrade head
else
  log "Migrations nao executadas. Use RUN_MIGRATIONS=1 apenas quando houver migracao revisada."
fi

# Seed do corpus RAG da "Bíblia de Conhecimento EJC" (situações + modelos,
# incluindo o Volume III) — idempotente (dedup por chave_origem). Roda DEPOIS
# das migrations (depende das tabelas knowledge_*). NÃO-FATAL de propósito: o
# app funciona sem o corpus, então uma falha aqui é logada e o deploy segue —
# o `if ... then` isenta o comando do `set -e`/trap ERR (sem rollback falso).
if [ "$RUN_SEEDS" = "1" ]; then
  log "RUN_SEEDS=1: aplicando seed da Biblia de Conhecimento EJC (nao-fatal)"
  if docker compose exec -T backend python scripts/seed_biblia_ejc.py; then
    log "Seed da Biblia concluido."
  else
    log "AVISO: seed da Biblia falhou (nao-fatal) — deploy segue; app opera sem o corpus. Rode manualmente: docker compose exec backend python scripts/seed_biblia_ejc.py"
  fi
else
  log "Seeds nao executados. Use RUN_SEEDS=1 para ingerir o corpus da Biblia (situacoes + modelos + Volume III)."
fi

log "Subindo frontend"
docker rm -f ejc_frontend >/dev/null 2>&1 || true
docker compose up -d --no-deps frontend

sleep 8
EJC_DOMAIN="$DOMAIN" bash scripts/post_deploy_check.sh

trap - ERR
log "Deploy seguro concluido com sucesso."
