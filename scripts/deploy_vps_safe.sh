#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/ejc}"
DOMAIN="${EJC_DOMAIN:-ejc.depaulateixeira.adv.br}"
RUN_MIGRATIONS="${RUN_MIGRATIONS:-0}"
MIGRATIONS_BACKWARD_COMPATIBLE="${MIGRATIONS_BACKWARD_COMPATIBLE:-0}"
RUN_SEEDS="${RUN_SEEDS:-0}"
# Produção exige configuração efetiva e prova recente do backup cifrado.
# Use 0 somente em contingência formalmente registrada.
ENSURE_DAILY_BACKUP="${ENSURE_DAILY_BACKUP:-1}"

cd "$APP_DIR"

timestamp() { date +"%Y%m%d_%H%M%S"; }
log() { echo "[$(date '+%F %T')] $*"; }

ROLLBACK_SUFFIX="$(timestamp)"
OLD_BACKEND_IMAGE=""
OLD_FRONTEND_IMAGE=""
OLD_BACKEND_TAG=""
OLD_FRONTEND_TAG=""
DEPLOY_MUTATED=0

cleanup_rollback_tags() {
  if [ -n "${OLD_BACKEND_TAG:-}" ]; then
    docker image rm "$OLD_BACKEND_TAG" >/dev/null 2>&1 || true
  fi
  if [ -n "${OLD_FRONTEND_TAG:-}" ]; then
    docker image rm "$OLD_FRONTEND_TAG" >/dev/null 2>&1 || true
  fi
}

rollback() {
  local original_rc=$?
  trap - ERR
  set +e

  if [ "$DEPLOY_MUTATED" != "1" ]; then
    log "Falha antes de qualquer mutação do runtime (rc=${original_rc}); aplicação anterior permanece intacta."
    cleanup_rollback_tags
    exit "$original_rc"
  fi

  log "Deploy falhou (rc=${original_rc}). Restaurando imagens anteriores."
  if [ -n "${OLD_BACKEND_TAG:-}" ]; then
    docker tag "$OLD_BACKEND_TAG" ejc-backend:latest
  elif [ -n "${OLD_BACKEND_IMAGE:-}" ]; then
    docker tag "$OLD_BACKEND_IMAGE" ejc-backend:latest
  else
    log "ERRO CRÍTICO: imagem anterior do backend indisponível."
  fi

  if [ -n "${OLD_FRONTEND_TAG:-}" ]; then
    docker tag "$OLD_FRONTEND_TAG" ejc-frontend:latest
  elif [ -n "${OLD_FRONTEND_IMAGE:-}" ]; then
    docker tag "$OLD_FRONTEND_IMAGE" ejc-frontend:latest
  else
    log "ERRO CRÍTICO: imagem anterior do frontend indisponível."
  fi

  RUN_MIGRATIONS=0 docker compose up -d --no-deps --force-recreate \
    backend worker frontend
  sleep 8
  if bash "$APP_DIR/scripts/post_deploy_check.sh"; then
    log "Rollback confirmado pelo post-deploy check."
  else
    log "ERRO CRÍTICO: imagens anteriores restauradas, mas o post-deploy check falhou."
  fi
  log "Tags de rollback preservadas para investigação: ${OLD_BACKEND_TAG:-sem-backend-tag} ${OLD_FRONTEND_TAG:-sem-frontend-tag}"
  exit "$original_rc"
}

# Uma política rejeitada não deve simular deploy/rollback. O schema só pode ser
# alterado automaticamente quando a análise do commit aprovado o classificou como
# expand-only e compatível com a aplicação anterior.
if [ "$RUN_MIGRATIONS" = "1" ] && [ "$MIGRATIONS_BACKWARD_COMPATIBLE" != "1" ]; then
  cat >&2 <<'EOF'
RUN_MIGRATIONS=1 foi solicitado sem MIGRATIONS_BACKWARD_COMPATIBLE=1.
O rollback restaura imagens, não schema. Reestruture a migration em expand/contract
ou submeta uma janela de manutenção específica; o deploy automático foi bloqueado.
EOF
  exit 2
fi

log "EJC deploy seguro iniciado para ${DOMAIN}"
[ -f .env ] || { echo "Arquivo .env ausente em ${APP_DIR}" >&2; exit 1; }
docker compose config >"/tmp/ejc_compose_config_$(timestamp).txt"

OLD_BACKEND_IMAGE="$(docker inspect -f '{{.Image}}' ejc_backend 2>/dev/null || true)"
OLD_FRONTEND_IMAGE="$(docker inspect -f '{{.Image}}' ejc_frontend 2>/dev/null || true)"
log "Imagem backend anterior: ${OLD_BACKEND_IMAGE:-indisponível}"
log "Imagem frontend anterior: ${OLD_FRONTEND_IMAGE:-indisponível}"

# Tags imutáveis impedem que o build de :latest torne a versão anterior órfã.
if [ -n "$OLD_BACKEND_IMAGE" ]; then
  OLD_BACKEND_TAG="ejc-backend:rollback-${ROLLBACK_SUFFIX}"
  docker tag "$OLD_BACKEND_IMAGE" "$OLD_BACKEND_TAG"
fi
if [ -n "$OLD_FRONTEND_IMAGE" ]; then
  OLD_FRONTEND_TAG="ejc-frontend:rollback-${ROLLBACK_SUFFIX}"
  docker tag "$OLD_FRONTEND_IMAGE" "$OLD_FRONTEND_TAG"
fi

trap rollback ERR

log "Gerando backup pré-deploy integral e cifrado"
bash scripts/backup.sh

# O frontend é compilado primeiro: falha de TypeScript não deve substituir a API.
DEPLOY_MUTATED=1
log "Build frontend"
docker compose build frontend
log "Build backend e worker"
docker compose build backend worker

# Expand/contract: a aplicação antiga continua atendendo enquanto a nova imagem
# executa a migration em container efêmero. Se a migration falhar, o runtime antigo
# permanece ativo; se passar, o schema expandido continua compatível com o rollback.
if [ "$RUN_MIGRATIONS" = "1" ]; then
  log "Aplicando migration expand-only antes da troca da API"
  docker compose run --rm --no-deps -T backend alembic upgrade head
else
  log "Nenhuma migration pendente; schema preservado."
fi

log "Subindo backend novo sem migration automática no entrypoint"
RUN_MIGRATIONS=0 docker compose up -d --no-deps --force-recreate backend
backend_ok=0
for _ in $(seq 1 12); do
  sleep 5
  if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    backend_ok=1
    break
  fi
done
[ "$backend_ok" = "1" ] || { log "Backend não respondeu em 60s"; exit 1; }

log "Atualizando worker"
RUN_MIGRATIONS=0 docker compose up -d --no-deps --force-recreate worker

if [ "$ENSURE_DAILY_BACKUP" = "1" ]; then
  log "Garantindo agendamento e prova recente do backup cifrado"
  bash scripts/backup/ativar_backup.sh
else
  log "AVISO CRÍTICO: ENSURE_DAILY_BACKUP=0 — garantia diária ignorada por contingência."
fi

# Seeds são idempotentes e não fatais; falha não invalida o runtime já saudável.
if [ "$RUN_SEEDS" = "1" ]; then
  log "Aplicando seed da Bíblia de Conhecimento EJC (não fatal)"
  if docker compose exec -T backend python scripts/seed_biblia_ejc.py; then
    log "Seed da Bíblia concluído."
  else
    log "AVISO: seed da Bíblia falhou; execução manual será necessária."
  fi

  log "Semeando base jurídica real (não fatal)"
  if docker compose exec -T backend python -m app.seeds.base_juridica_seed --incluir-legislacao; then
    log "Seed da base jurídica real concluído."
  else
    log "AVISO: seed da base jurídica real falhou; súmulas de boot permanecem disponíveis."
  fi
else
  log "Seeds não executados neste deploy."
fi

# O acervo vigente precisa permanecer aprovado e indexado. Esta etapa é
# bloqueante; rollback de imagem é seguro porque a operação é idempotente.
log "Aprovando e indexando pendências da Base de Conhecimento"
docker compose exec -T backend python -m scripts.reparar_conhecimento_rag --batch-size 50

log "Subindo frontend"
docker rm -f ejc_frontend >/dev/null 2>&1 || true
RUN_MIGRATIONS=0 docker compose up -d --no-deps --force-recreate frontend

sleep 8
EJC_DOMAIN="$DOMAIN" bash scripts/post_deploy_check.sh

trap - ERR
cleanup_rollback_tags
log "Deploy seguro concluído com sucesso."
