#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/ejc}"
DOMAIN="${EJC_DOMAIN:-ejc.depaulateixeira.adv.br}"
RUN_MIGRATIONS="${RUN_MIGRATIONS:-0}"

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
sleep 10
curl -fsS http://127.0.0.1:8000/api/health >/dev/null

if [ "$RUN_MIGRATIONS" = "1" ]; then
  log "RUN_MIGRATIONS=1: aplicando Alembic"
  docker compose exec -T backend alembic upgrade head
else
  log "Migrations nao executadas. Use RUN_MIGRATIONS=1 apenas quando houver migracao revisada."
fi

log "Subindo frontend"
docker rm -f ejc_frontend >/dev/null 2>&1 || true
docker compose up -d --no-deps frontend

sleep 8
EJC_DOMAIN="$DOMAIN" bash scripts/post_deploy_check.sh

trap - ERR
log "Deploy seguro concluido com sucesso."
