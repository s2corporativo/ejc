#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/ejc}"
DOMAIN="${EJC_DOMAIN:-ejc.depaulateixeira.adv.br}"
RUN_MIGRATIONS="${RUN_MIGRATIONS:-0}"
RUN_SEEDS="${RUN_SEEDS:-0}"
# Política de produção: todo deploy garante configuração efetiva e prova recente
# do backup cifrado no Google Drive. Use 0 somente em contingência declarada.
ENSURE_DAILY_BACKUP="${ENSURE_DAILY_BACKUP:-1}"

cd "$APP_DIR"

timestamp() { date +"%Y%m%d_%H%M%S"; }
log() { echo "[$(date '+%F %T')] $*"; }

ROLLBACK_SUFFIX="$(timestamp)"
OLD_BACKEND_IMAGE=""
OLD_FRONTEND_IMAGE=""
OLD_BACKEND_TAG=""
OLD_FRONTEND_TAG=""

cleanup_rollback_tags() {
  if [ -n "${OLD_BACKEND_TAG:-}" ]; then
    docker image rm "$OLD_BACKEND_TAG" >/dev/null 2>&1 || true
  fi
  if [ -n "${OLD_FRONTEND_TAG:-}" ]; then
    docker image rm "$OLD_FRONTEND_TAG" >/dev/null 2>&1 || true
  fi
}

rollback() {
  log "Deploy falhou. Iniciando rollback seguro."
  if [ -n "${OLD_BACKEND_TAG:-}" ]; then
    docker tag "$OLD_BACKEND_TAG" ejc-backend:latest || true
  elif [ -n "${OLD_BACKEND_IMAGE:-}" ]; then
    docker tag "$OLD_BACKEND_IMAGE" ejc-backend:latest || true
  fi
  if [ -n "${OLD_FRONTEND_TAG:-}" ]; then
    docker tag "$OLD_FRONTEND_TAG" ejc-frontend:latest || true
  elif [ -n "${OLD_FRONTEND_IMAGE:-}" ]; then
    docker tag "$OLD_FRONTEND_IMAGE" ejc-frontend:latest || true
  fi
  docker compose up -d --no-deps backend worker frontend || true
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

# Preserva tags imutáveis antes do build. Sem isso, o Docker pode remover a
# imagem anterior quando a tag :latest é substituída, inviabilizando o rollback.
if [ -n "$OLD_BACKEND_IMAGE" ]; then
  OLD_BACKEND_TAG="ejc-backend:rollback-${ROLLBACK_SUFFIX}"
  docker tag "$OLD_BACKEND_IMAGE" "$OLD_BACKEND_TAG"
fi
if [ -n "$OLD_FRONTEND_IMAGE" ]; then
  OLD_FRONTEND_TAG="ejc-frontend:rollback-${ROLLBACK_SUFFIX}"
  docker tag "$OLD_FRONTEND_IMAGE" "$OLD_FRONTEND_TAG"
fi

log "Backup antes do deploy"
bash scripts/backup.sh

# O frontend é compilado primeiro. Assim, uma falha de TypeScript não substitui
# a imagem do backend em produção e evita versão mista entre API e interface.
log "Build frontend"
docker compose build frontend
log "Build backend"
docker compose build backend worker

log "Subindo backend"
docker compose up -d --no-deps backend
# Boot frio pós-build leva mais que 10s: espera até 60s (12 x 5s) antes de
# declarar falha.
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

# O worker usa a mesma imagem do backend e precisa ser recriado a cada deploy.
log "Atualizando worker"
docker compose up -d --no-deps worker

# Backup diário offsite é requisito de produção (continuidade / gate G7), não
# opção documental. O helper garante o .env, recria o backend (restart não
# recarrega env_file), confirma o scheduler e executa uma prova integral.
#
# ESTRITO por PADRÃO: se a PROVA do backup falhar, o deploy ABORTA (rollback) —
# o requisito de continuidade permanece o default e nenhuma release "esconde"
# uma falha de backup. A falha da prova pode ter causa-raiz EXTERNA (credencial/
# escopo do Google Drive, ex.: invalid_scope) — rastreada na issue #378.
#
# CONTINGÊNCIA EXPLÍCITA (opt-in, NÃO-certificada): exportar
# BACKUP_PROVA_CONTINGENCIA=1 permite que um app SAUDÁVEL siga no ar mesmo com a
# prova de backup falhando — com AVISO CRÍTICO e marcando a release como NÃO
# CERTIFICADA (não satisfaz o gate G7 de continuidade). É decisão consciente do
# operador, não o comportamento silencioso padrão.
if [ "$ENSURE_DAILY_BACKUP" = "1" ]; then
  log "Garantindo backup diário cifrado no Google Drive"
  if bash scripts/backup/ativar_backup.sh; then
    log "Backup diário no Drive comprovado."
  elif [ "${BACKUP_PROVA_CONTINGENCIA:-0}" = "1" ]; then
    log "AVISO CRÍTICO / RELEASE NÃO CERTIFICADA: a PROVA do backup diário no Drive FALHOU e BACKUP_PROVA_CONTINGENCIA=1 — o deploy do app segue por CONTINGÊNCIA consciente. Continuidade NÃO garantida (gate G7 não satisfeito). Verifique credencial/escopo do Google Drive (escopo de ESCRITA https://www.googleapis.com/auth/drive) e a issue #378."
  else
    log "ERRO: a PROVA do backup diário no Drive FALHOU — abortando o deploy (rollback). Backup é requisito de continuidade (gate G7). Causa-raiz provável: credencial/escopo do Google Drive (issue #378). Para prosseguir por CONTINGÊNCIA consciente (release NÃO certificada), reexecute com BACKUP_PROVA_CONTINGENCIA=1."
    false
  fi
else
  log "AVISO CRÍTICO: ENSURE_DAILY_BACKUP=0 — garantia de backup diário foi ignorada por contingência."
fi

# Seed do corpus RAG da "Bíblia de Conhecimento EJC" — idempotente e não fatal.
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

# Política permanente: todo documento vigente da Base de Conhecimento deve estar
# aprovado para uso pela IA. O reparo é idempotente e também completa embeddings
# ausentes; falha aqui interrompe o deploy para não publicar uma inteligência
# jurídica com acervo silenciosamente indisponível.
log "Aprovando e indexando pendencias da Base de Conhecimento"
docker compose exec -T backend python -m scripts.reparar_conhecimento_rag --batch-size 50

log "Subindo frontend"
docker rm -f ejc_frontend >/dev/null 2>&1 || true
docker compose up -d --no-deps frontend

sleep 8
EJC_DOMAIN="$DOMAIN" bash scripts/post_deploy_check.sh

trap - ERR
cleanup_rollback_tags
log "Deploy seguro concluido com sucesso."
