#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/ejc}"
DOMAIN="${EJC_DOMAIN:-ejc.depaulateixeira.adv.br}"
RUN_MIGRATIONS="${RUN_MIGRATIONS:-0}"
MIGRATIONS_BACKWARD_COMPATIBLE="${MIGRATIONS_BACKWARD_COMPATIBLE:-0}"
RUN_SEEDS="${RUN_SEEDS:-0}"
ENSURE_DAILY_BACKUP="${ENSURE_DAILY_BACKUP:-1}"
REQUIRE_PREDEPLOY_BACKUP="${REQUIRE_PREDEPLOY_BACKUP:-0}"

cd "$APP_DIR"

timestamp() { date +"%Y%m%d_%H%M%S"; }
log() { echo "[$(date '+%F %T')] $*"; }

ROLLBACK_SUFFIX="$(timestamp)"
OLD_BACKEND_IMAGE=""
OLD_WORKER_IMAGE=""
OLD_FRONTEND_IMAGE=""
OLD_BACKEND_REF=""
OLD_WORKER_REF=""
OLD_FRONTEND_REF=""
OLD_BACKEND_TAG=""
OLD_WORKER_TAG=""
OLD_FRONTEND_TAG=""
DEPLOY_MUTATED=0

cleanup_rollback_tags() {
  for tag in "${OLD_BACKEND_TAG:-}" "${OLD_WORKER_TAG:-}" "${OLD_FRONTEND_TAG:-}"; do
    if [ -n "$tag" ]; then
      docker image rm "$tag" >/dev/null 2>&1 || true
    fi
  done
}

_restore_image() {
  local immutable_tag="$1" image_id="$2" target_ref="$3" label="$4"
  if [ -n "$immutable_tag" ] && [ -n "$target_ref" ]; then
    docker tag "$immutable_tag" "$target_ref"
  elif [ -n "$image_id" ] && [ -n "$target_ref" ]; then
    docker tag "$image_id" "$target_ref"
  else
    log "ERRO CRÍTICO: imagem ou referência anterior de ${label} indisponível."
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

  log "Deploy falhou (rc=${original_rc}). Restaurando backend, worker e frontend."
  # O rollback recria os containers a partir das imagens ANTERIORES, mas o
  # GIT_SHA exportado ainda é o do deploy que falhou — sem isto, o backend
  # restaurado anunciaria em /api/health o SHA que NÃO está rodando, que é
  # exatamente a mentira que esta instrumentação existe para evitar.
  export GIT_SHA="${OLD_GIT_SHA:-desconhecido}"
  log "Rollback publica novamente o commit anterior: ${GIT_SHA}"
  _restore_image "$OLD_BACKEND_TAG" "$OLD_BACKEND_IMAGE" "$OLD_BACKEND_REF" "backend"
  _restore_image "$OLD_WORKER_TAG" "$OLD_WORKER_IMAGE" "$OLD_WORKER_REF" "worker"
  _restore_image "$OLD_FRONTEND_TAG" "$OLD_FRONTEND_IMAGE" "$OLD_FRONTEND_REF" "frontend"

  RUN_MIGRATIONS=0 docker compose up -d --no-deps --force-recreate \
    backend worker frontend
  sleep 8
  if bash "$APP_DIR/scripts/post_deploy_check.sh"; then
    log "Rollback confirmado pelo post-deploy check."
  else
    log "ERRO CRÍTICO: imagens anteriores restauradas, mas o post-deploy check falhou."
  fi
  log "Tags de rollback preservadas para investigação: ${OLD_BACKEND_TAG:-sem-backend-tag} ${OLD_WORKER_TAG:-sem-worker-tag} ${OLD_FRONTEND_TAG:-sem-frontend-tag}"
  exit "$original_rc"
}

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

# Migra valores OBSOLETOS do .env preservado (modelo Groq depreciado etc.).
# O .env sobrevive ao deploy por desenho, então trocar o default no código não
# alcança a VPS. Idempotente, com backup 600 e sem imprimir segredos.
if [ -f scripts/migrar_env_obsoletos.sh ]; then
  bash scripts/migrar_env_obsoletos.sh .env | while IFS= read -r linha; do
    log "$linha"
  done
fi
# SYS-097 (correção originada no PR #497, adotada aqui): validar a composição
# SEM persistir a config expandida. O antigo `docker compose config >/tmp/...txt`
# gravava TODOS os segredos interpolados (senha do Postgres, chaves de API,
# tokens) em claro num arquivo world-readable de /tmp que nunca era removido —
# a cada deploy. `--quiet` valida sintaxe e interpolação sem emitir nada.
docker compose config --quiet

OLD_BACKEND_IMAGE="$(docker inspect -f '{{.Image}}' ejc_backend 2>/dev/null || true)"
OLD_WORKER_IMAGE="$(docker inspect -f '{{.Image}}' ejc_worker 2>/dev/null || true)"
OLD_FRONTEND_IMAGE="$(docker inspect -f '{{.Image}}' ejc_frontend 2>/dev/null || true)"
OLD_BACKEND_REF="$(docker inspect -f '{{.Config.Image}}' ejc_backend 2>/dev/null || true)"
OLD_WORKER_REF="$(docker inspect -f '{{.Config.Image}}' ejc_worker 2>/dev/null || true)"
OLD_FRONTEND_REF="$(docker inspect -f '{{.Config.Image}}' ejc_frontend 2>/dev/null || true)"
log "Imagem backend anterior: ${OLD_BACKEND_IMAGE:-indisponível} (${OLD_BACKEND_REF:-sem-ref})"
log "Imagem worker anterior: ${OLD_WORKER_IMAGE:-indisponível} (${OLD_WORKER_REF:-sem-ref})"
log "Imagem frontend anterior: ${OLD_FRONTEND_IMAGE:-indisponível} (${OLD_FRONTEND_REF:-sem-ref})"

if [ -n "$OLD_BACKEND_IMAGE" ]; then
  OLD_BACKEND_TAG="ejc-backend:rollback-${ROLLBACK_SUFFIX}"
  docker tag "$OLD_BACKEND_IMAGE" "$OLD_BACKEND_TAG"
fi
if [ -n "$OLD_WORKER_IMAGE" ]; then
  OLD_WORKER_TAG="ejc-worker:rollback-${ROLLBACK_SUFFIX}"
  docker tag "$OLD_WORKER_IMAGE" "$OLD_WORKER_TAG"
fi
if [ -n "$OLD_FRONTEND_IMAGE" ]; then
  OLD_FRONTEND_TAG="ejc-frontend:rollback-${ROLLBACK_SUFFIX}"
  docker tag "$OLD_FRONTEND_IMAGE" "$OLD_FRONTEND_TAG"
fi

trap rollback ERR

log "Verificando pré-requisitos de backup"
# O gate bloqueia SOMENTE se a prova LOCAL cifrada falhar (backup.sh != 0).
# Offsite falho com prova local presente → exit 0 + "offsite_ok": false no
# JSON: o deploy prossegue com AVISO GRAVE no log e no step summary.
BACKUP_SAIDA=""
if BACKUP_SAIDA="$(bash scripts/backup.sh)"; then
  [ -n "$BACKUP_SAIDA" ] && printf '%s\n' "$BACKUP_SAIDA"
  log "Backup pré-deploy concluído."
  if printf '%s' "$BACKUP_SAIDA" | grep -q '"offsite_ok": false'; then
    BACKUP_OFFSITE_DESTINO="$(printf '%s' "$BACKUP_SAIDA" | sed -n 's/.*"destino": "\([^"]*\)".*/\1/p')"
    BACKUP_OFFSITE_ERRO="$(printf '%s' "$BACKUP_SAIDA" | sed -n 's/.*"offsite_erro": "\([^"]*\)".*/\1/p')"
    AVISO_OFFSITE="AVISO GRAVE: backup offsite falhou (destino ${BACKUP_OFFSITE_DESTINO:-desconhecido}): ${BACKUP_OFFSITE_ERRO:-erro não informado} — deploy prossegue com prova local; corrija o destino offsite"
    log "$AVISO_OFFSITE"
    if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
      printf '> :warning: %s\n' "$AVISO_OFFSITE" >>"$GITHUB_STEP_SUMMARY"
    fi
  fi
else
  [ -n "$BACKUP_SAIDA" ] && printf '%s\n' "$BACKUP_SAIDA"
  if [ "$REQUIRE_PREDEPLOY_BACKUP" = "1" ]; then
    log "ERRO CRÍTICO: backup pré-deploy obrigatório falhou."
    log "Deploy bloqueado antes de qualquer mutação do runtime."
    false
  fi
  log "AVISO: backup pré-deploy não executou (credenciais ou config incompleta)."
  log "AVISO: modo de contingência permissivo; deploy prossegue sem prova nova de backup."
fi

DEPLOY_MUTATED=1
# SHA do commit sendo publicado: entra no container via docker-compose.yml e é
# conferido no /api/health depois da troca. Sem isso não havia como provar qual
# código está no ar — a origem do "minha alteração não aparece no sistema".
GIT_SHA="${TARGET_SHA:-$(git rev-parse HEAD 2>/dev/null || echo desconhecido)}"
[ -z "$GIT_SHA" ] && GIT_SHA="desconhecido"
if [ "$GIT_SHA" = "desconhecido" ]; then
  # O workflow exclui .git/ do rsync, então numa execução MANUAL na VPS sem
  # TARGET_SHA não há como saber o commit. O deploy continua válido — o que
  # se perde é a PROVA. Avisa alto e desliga a conferência, em vez de comparar
  # duas incógnitas e imprimir "confirmado: desconhecido", que seria um falso
  # positivo justamente no caminho mais sujeito a erro.
  log "AVISO: commit indeterminado (sem TARGET_SHA e sem .git)."
  log "AVISO: a conferência do commit publicado fica INDISPONÍVEL neste deploy."
  log "AVISO: informe TARGET_SHA=<sha> para ter a prova de qual código subiu."
fi
export GIT_SHA
log "Commit a publicar: ${GIT_SHA}"

# SHA que está no ar AGORA — usado pelo rollback para republicar a verdade.
OLD_GIT_SHA="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' \
  ejc_backend 2>/dev/null | sed -n 's/^GIT_SHA=//p' | head -1)"
log "Commit atualmente publicado: ${OLD_GIT_SHA:-indisponível}"

log "Build frontend"
docker compose build frontend
log "Build backend e worker"
docker compose build backend worker

# Expand/contract: a aplicação antiga atende enquanto a imagem nova executa a
# migration em container efêmero. O schema expandido permanece compatível com o
# backend/worker anteriores se for necessário restaurar as imagens.
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

# PROVA do commit publicado: o backend precisa se identificar com o MESMO SHA
# que acabou de ser construído. Divergência aqui significa container antigo em
# pé (imagem reaproveitada, --force-recreate sem rebuild, bind mount apontando
# para outro diretório) — o deploy responderia "ok" com o código velho no ar.
COMMIT_NO_AR="$(curl -fsS http://127.0.0.1:8000/api/health 2>/dev/null \
  | sed -n 's/.*"commit"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
if [ "$GIT_SHA" = "desconhecido" ]; then
  # Sem SHA de referência não há o que conferir; o aviso já foi dado no início.
  log "Conferência do commit publicado PULADA (commit de origem indeterminado)."
elif [ "$COMMIT_NO_AR" = "$GIT_SHA" ]; then
  log "Commit publicado confirmado pelo /api/health: ${COMMIT_NO_AR}"
elif [ -z "$COMMIT_NO_AR" ] || [ "$COMMIT_NO_AR" = "desconhecido" ]; then
  # O backend construído a partir deste commit SEMPRE expõe o campo. Resposta
  # sem SHA significa container antigo ainda em pé, imagem errada ou build que
  # não pegou — exatamente o que esta verificação existe para detectar. Falhar
  # aqui aciona o rollback; aceitar seria declarar sucesso sem prova nenhuma.
  log "ERRO CRÍTICO: /api/health respondeu sem o commit (valor: '${COMMIT_NO_AR:-vazio}')."
  log "O container em pé não é o que acabou de ser construído."
  exit 1
else
  log "ERRO CRÍTICO: backend no ar declara commit ${COMMIT_NO_AR}, esperado ${GIT_SHA}."
  log "O container não está executando o código recém-construído."
  exit 1
fi

log "Atualizando worker"
RUN_MIGRATIONS=0 docker compose up -d --no-deps --force-recreate worker

if [ "$ENSURE_DAILY_BACKUP" = "1" ]; then
  log "Garantindo agendamento e prova recente do backup cifrado"
  if bash scripts/backup/ativar_backup.sh; then
    log "Backup diário verificado com sucesso."
  else
    if [ "$REQUIRE_PREDEPLOY_BACKUP" = "1" ]; then
      log "ERRO CRÍTICO: ativação/verificação obrigatória do backup diário falhou."
      log "Deploy será revertido para preservar a política de continuidade."
      false
    fi
    log "AVISO: ativação/verificação do backup diário falhou; deploy não será revertido."
    log "AVISO: investigue as credenciais BACKUP_GOOGLE_DRIVE_* no .env da VPS."
  fi
else
  if [ "$REQUIRE_PREDEPLOY_BACKUP" = "1" ]; then
    log "ERRO CRÍTICO: ENSURE_DAILY_BACKUP=0 é incompatível com REQUIRE_PREDEPLOY_BACKUP=1."
    false
  fi
  log "AVISO CRÍTICO: ENSURE_DAILY_BACKUP=0 — garantia diária ignorada por contingência."
fi

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
