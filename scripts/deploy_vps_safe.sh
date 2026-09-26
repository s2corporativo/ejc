#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-/opt/ejc}"
DOMAIN="${EJC_DOMAIN:-ejc.depaulateixeira.adv.br}"
RUN_MIGRATIONS="${RUN_MIGRATIONS:-0}"
MIGRATIONS_BACKWARD_COMPATIBLE="${MIGRATIONS_BACKWARD_COMPATIBLE:-0}"
RUN_SEEDS="${RUN_SEEDS:-0}"
DEPLOY_SCOPE="${DEPLOY_SCOPE:-full}"
ENSURE_DAILY_BACKUP="${ENSURE_DAILY_BACKUP:-1}"
REQUIRE_PREDEPLOY_BACKUP="${REQUIRE_PREDEPLOY_BACKUP:-1}"
MIN_FREE_GB="${MIN_FREE_GB:-20}"
MIGRATION_DATABASE_URL_FILE="${MIGRATION_DATABASE_URL_FILE:-/opt/ejc/secrets/migration_database_url}"

log() { echo "[$(date '+%F %T')] $*"; }
timestamp() { date +"%Y%m%d_%H%M%S"; }
die_policy() { printf 'ERRO DE POLÍTICA: %s\n' "$*" >&2; exit 2; }

case "$REQUIRE_PREDEPLOY_BACKUP" in 0|1) ;; *) die_policy "REQUIRE_PREDEPLOY_BACKUP deve ser 0 ou 1";; esac
case "$ENSURE_DAILY_BACKUP" in 0|1) ;; *) die_policy "ENSURE_DAILY_BACKUP deve ser 0 ou 1";; esac
case "$DEPLOY_SCOPE" in frontend|full) ;; *) die_policy "DEPLOY_SCOPE deve ser frontend ou full";; esac
[[ "$MIN_FREE_GB" =~ ^[1-9][0-9]*$ ]] || die_policy "MIN_FREE_GB deve ser inteiro >= 1"
if [ "$REQUIRE_PREDEPLOY_BACKUP" = "1" ] && [ "$ENSURE_DAILY_BACKUP" != "1" ]; then
  die_policy "ENSURE_DAILY_BACKUP=0 é incompatível com REQUIRE_PREDEPLOY_BACKUP=1"
fi
command -v mktemp >/dev/null 2>&1 || die_policy "mktemp é obrigatório para snapshot transacional do .env"

[ -f "$SCRIPT_DIR/deploy_lock.sh" ] || die_policy "scripts/deploy_lock.sh ausente"
# shellcheck source=deploy_lock.sh
source "$SCRIPT_DIR/deploy_lock.sh"
lock_rc=0
ejc_deploy_lock_acquire "$APP_DIR" || lock_rc=$?
case "$lock_rc" in
  0) ;;
  75)
    log "Outro deploy EJC já está em execução; nenhuma mutação foi iniciada."
    exit 75
    ;;
  *) die_policy "não foi possível adquirir/revalidar mutex host-level" ;;
esac

cd "$APP_DIR"

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
OLD_GIT_SHA=""
ENV_ROLLBACK_FILE=""
DEPLOYED_SHA_TMP="$APP_DIR/.deployed_sha.new.$"
FRONTEND_DEPLOYED_SHA_TMP="$APP_DIR/.frontend_deployed_sha.new.$"
ROLLBACK_ARMED=0
FRONTEND_ONLY_ROLLBACK_ARMED=0
FRONTEND_ROLLBACK_TAG=""
FRONTEND_OLD_REF=""
ENV_MUTATED=0
ENV_WAS_IMMUTABLE=0
IMAGES_MUTATED=0
DEPLOY_MUTATED=0

cleanup_rollback_tags() {
  for tag in "${OLD_BACKEND_TAG:-}" "${OLD_WORKER_TAG:-}" "${OLD_FRONTEND_TAG:-}"; do
    [ -n "$tag" ] || continue
    docker image rm "$tag" >/dev/null 2>&1 || true
  done
}

cleanup_temp_files() {
  [ -z "$ENV_ROLLBACK_FILE" ] || rm -f -- "$ENV_ROLLBACK_FILE" >/dev/null 2>&1 || true
  rm -f -- "$DEPLOYED_SHA_TMP" "$FRONTEND_DEPLOYED_SHA_TMP" >/dev/null 2>&1 || true
}

# Bloqueio/registro da imutabilidade do .env (chattr +i): sem detecção, o
# deploy falha no meio com produção já tocada e o rollback não consegue
# restaurar o snapshot. As funções abaixo centralizam unlock/relock.
detect_env_immutable() {
  ENV_WAS_IMMUTABLE=0
  command -v lsattr >/dev/null 2>&1 || return 0
  local attrs
  attrs="$(lsattr -d .env 2>/dev/null | awk '{print $1}' || true)"
  case "$attrs" in
    *i*)
      command -v chattr >/dev/null 2>&1         || die_policy ".env está imutável, mas chattr não está disponível"
      ENV_WAS_IMMUTABLE=1
      ;;
  esac
}

unlock_env_if_needed() {
  [ "$ENV_WAS_IMMUTABLE" = "1" ] || return 0
  chattr -i .env
}

relock_env_if_needed() {
  [ "$ENV_WAS_IMMUTABLE" = "1" ] || return 0
  chattr +i .env
}

# Persistir o SHA aprovado evita que um docker compose up/restart posterior
# recarregue um GIT_SHA antigo do .env e faça /api/health anunciar artefato
# incorreto. Garante exatamente UM GIT_SHA= no .env (dedup de entradas legadas).
persist_git_sha_env() {
  python3 - "$GIT_SHA" <<'PY'
from pathlib import Path
import sys

path = Path(".env")
sha = sys.argv[1]
lines = path.read_text(encoding="utf-8").splitlines()
out = []
seen = False
for line in lines:
    if line.startswith("GIT_SHA="):
        if not seen:
            out.append(f"GIT_SHA={sha}")
            seen = True
        continue
    out.append(line)
if not seen:
    out.append(f"GIT_SHA={sha}")
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
}

# Restaura o snapshot transacional do .env somente quando o conteúdo mudou;
# se estiver idêntico, limita-se a garantir modo 0600 sem reescrever o arquivo.
restore_env() {
  [ "$ENV_MUTATED" = "1" ] || return 0
  [ -n "$ENV_ROLLBACK_FILE" ] && [ -s "$ENV_ROLLBACK_FILE" ] \
    || { log "ERRO CRÍTICO: snapshot transacional do .env ausente."; return 1; }

  # Se o arquivo era originalmente imutável, o caminho normal de deploy já
  # reaplicou +i antes de build/cutover. Qualquer rollback posterior precisa
  # remover +i novamente ANTES de restaurar o snapshot e reaplicá-lo ao final.
  unlock_env_if_needed || return 1

  local rc=0
  if cmp -s -- "$ENV_ROLLBACK_FILE" .env; then
    if [ "$(stat -c '%a' .env 2>/dev/null || true)" != "600" ]; then
      chmod 600 .env || rc=1
    fi
    if [ "$rc" -eq 0 ]; then
      log ".env permaneceu idêntico ao snapshot; conteúdo não foi reescrito e permissões seguras foram preservadas."
    fi
  else
    cp -- "$ENV_ROLLBACK_FILE" .env || rc=1
    if [ "$rc" -eq 0 ]; then
      chmod 600 .env || rc=1
    fi
    if [ "$rc" -eq 0 ]; then
      log ".env anterior restaurado a partir do snapshot transacional protegido."
    fi
  fi

  # Preserva a política original mesmo quando a restauração do conteúdo falha.
  relock_env_if_needed || rc=1
  return "$rc"
}

_restore_image() {
  local immutable_tag="$1" image_id="$2" target_ref="$3" label="$4"
  if [ -n "$immutable_tag" ] && [ -n "$target_ref" ]; then
    docker tag "$immutable_tag" "$target_ref"
  elif [ -n "$image_id" ] && [ -n "$target_ref" ]; then
    docker tag "$image_id" "$target_ref"
  else
    log "ERRO CRÍTICO: imagem ou referência anterior de ${label} indisponível."
    return 1
  fi
}

restore_previous_image_refs() {
  local rc=0
  _restore_image "$OLD_BACKEND_TAG" "$OLD_BACKEND_IMAGE" "$OLD_BACKEND_REF" "backend" || rc=1
  _restore_image "$OLD_WORKER_TAG" "$OLD_WORKER_IMAGE" "$OLD_WORKER_REF" "worker" || rc=1
  _restore_image "$OLD_FRONTEND_TAG" "$OLD_FRONTEND_IMAGE" "$OLD_FRONTEND_REF" "frontend" || rc=1
  return "$rc"
}

rollback_frontend_only() {
  local rc=0
  [ -n "$FRONTEND_ROLLBACK_TAG" ] && [ -n "$FRONTEND_OLD_REF" ] || return 1
  log "Restaurando somente o frontend anterior."
  docker tag "$FRONTEND_ROLLBACK_TAG" "$FRONTEND_OLD_REF" || rc=1
  docker rm -f ejc_frontend >/dev/null 2>&1 || true
  RUN_MIGRATIONS=0 docker compose up -d --no-deps --force-recreate frontend || rc=1
  sleep 5
  curl -fsS --connect-timeout 5 --max-time 15 http://127.0.0.1:8080/ >/dev/null 2>&1 || rc=1
  return "$rc"
}

rollback_transaction() {
  local original_rc="$1"
  set +e

  restore_env || log "ERRO CRÍTICO: restauração do .env ficou incompleta."

  if [ "$DEPLOY_MUTATED" = "1" ]; then
    log "Deploy falhou (rc=${original_rc}). Restaurando imagens e runtime anteriores."
    export GIT_SHA="${OLD_GIT_SHA:-desconhecido}"
    restore_previous_image_refs || log "ERRO CRÍTICO: restauração de referências de imagem ficou incompleta."
    RUN_MIGRATIONS=0 docker compose up -d --no-deps --force-recreate backend worker frontend
    sleep 8
    if bash "$APP_DIR/scripts/post_deploy_check.sh"; then
      log "Rollback confirmado pelo post-deploy check."
    else
      log "ERRO CRÍTICO: runtime anterior restaurado, mas post-deploy check falhou."
    fi
    log "Tags de rollback preservadas para investigação: ${OLD_BACKEND_TAG:-sem-backend-tag} ${OLD_WORKER_TAG:-sem-worker-tag} ${OLD_FRONTEND_TAG:-sem-frontend-tag}"
  elif [ "$IMAGES_MUTATED" = "1" ]; then
    if restore_previous_image_refs; then
      log "Falha antes da troca do runtime (rc=${original_rc}); referências de imagem anteriores restauradas sem reiniciar containers."
    else
      log "ERRO CRÍTICO: restauração das referências de imagem ficou incompleta."
    fi
    cleanup_rollback_tags
  else
    log "Falha antes de build/cutover (rc=${original_rc}); runtime anterior permaneceu intacto."
    cleanup_rollback_tags
  fi
  cleanup_temp_files
}

on_exit() {
  local rc=$?
  trap - EXIT INT TERM HUP
  if [ "$rc" -ne 0 ] && [ "$FRONTEND_ONLY_ROLLBACK_ARMED" = "1" ]; then
    rollback_frontend_only || log "ERRO CRÍTICO: rollback frontend-only ficou incompleto."
    cleanup_temp_files
  elif [ "$rc" -ne 0 ] && [ "$ROLLBACK_ARMED" = "1" ]; then
    rollback_transaction "$rc"
  else
    cleanup_temp_files
  fi
  exit "$rc"
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

if [ "$RUN_MIGRATIONS" = "1" ] && [ "$MIGRATIONS_BACKWARD_COMPATIBLE" != "1" ]; then
  cat >&2 <<'EOF'
RUN_MIGRATIONS=1 foi solicitado sem MIGRATIONS_BACKWARD_COMPATIBLE=1.
O rollback restaura imagens, não schema. Reestruture a migration em expand/contract
ou submeta uma janela de manutenção específica; o deploy automático foi bloqueado.
EOF
  exit 2
fi

connect_evolution_network_if_present() {
  local container="$1"
  # Evolution pertence a outro compose e mantém sua API sem exposição pública.
  # Se a rede externa existir, reconecta o container EJC após cada recreate.
  # Ausência da rede é neutra: WhatsApp é opt-in e o diagnóstico sinaliza isso.
  if docker network inspect evolution_net >/dev/null 2>&1; then
    if docker inspect "$container" >/dev/null 2>&1; then
      docker network connect evolution_net "$container" >/dev/null 2>&1 || true
    fi
  fi
}

log "EJC deploy seguro iniciado para ${DOMAIN}"
if [ "$REQUIRE_PREDEPLOY_BACKUP" = "0" ]; then
  log "AVISO CRÍTICO: REQUIRE_PREDEPLOY_BACKUP=0 foi definido explicitamente; contingência sem prova nova de backup está habilitada."
fi
[ -f .env ] || { echo "Arquivo .env ausente em ${APP_DIR}" >&2; exit 1; }

GIT_SHA="${TARGET_SHA:-$(git rev-parse HEAD 2>/dev/null || true)}"
[[ "$GIT_SHA" =~ ^[0-9a-f]{40}$ ]] \
  || die_policy "TARGET_SHA/HEAD deve ser SHA-1 completo de 40 caracteres hexadecimais; release sem identidade verificável foi bloqueada"
export GIT_SHA
log "Versão a publicar: ${GIT_SHA}"
log "Escopo autorizado: ${DEPLOY_SCOPE}"
if [ "$DEPLOY_SCOPE" = "frontend" ] && [ "$RUN_MIGRATIONS" = "1" ]; then
  die_policy "frontend-only é incompatível com migration pendente"
fi
if [ "$DEPLOY_SCOPE" = "frontend" ] && [ "$RUN_SEEDS" = "1" ]; then
  log "RUN_SEEDS=1 exige fluxo full; promovendo escopo antes de qualquer cutover."
  DEPLOY_SCOPE="full"
fi
if [ "$DEPLOY_SCOPE" = "frontend" ]; then
  frontend_image="$(docker inspect -f '{{.Image}}' ejc_frontend 2>/dev/null || true)"
  if [ -z "$frontend_image" ] || ! docker image inspect "$frontend_image" >/dev/null 2>&1; then
    log "Imagem atual do frontend não está disponível para rollback; usando fluxo full."
    DEPLOY_SCOPE="full"
  fi
fi
docker compose config --quiet

AVAIL_KB="$(df -Pk "${APP_DIR}" | awk 'NR==2 {print $4}')"
MIN_FREE_KB="$((MIN_FREE_GB * 1024 * 1024))"
if [ -z "$AVAIL_KB" ] || [ "$AVAIL_KB" -lt "$MIN_FREE_KB" ]; then
  log "ERRO CRÍTICO: espaço livre insuficiente para deploy (${AVAIL_KB:-0} KB; mínimo ${MIN_FREE_GB} GB)."
  log "Deploy bloqueado antes de backup/build para evitar ENOSPC em Docker/PostgreSQL."
  exit 1
fi
log "Gate de capacidade aprovado: mínimo ${MIN_FREE_GB} GB livres."

log "Verificando pré-requisitos de backup"
BACKUP_SAIDA=""
if BACKUP_SAIDA="$(bash scripts/backup.sh)"; then
  [ -n "$BACKUP_SAIDA" ] && printf '%s\n' "$BACKUP_SAIDA"
  log "Backup pré-deploy concluído."
if ! printf '%s' "$BACKUP_SAIDA" | grep -Eq '"local_ok"[[:space:]]*:[[:space:]]*true'; then
  log "ERRO CRÍTICO: backup não comprovou persistência local cifrada (local_ok=true)."
  log "Deploy bloqueado antes de qualquer mutação de .env/imagens/runtime."
  exit 1
fi
if printf '%s' "$BACKUP_SAIDA" | grep -Eq '"offsite_required"[[:space:]]*:[[:space:]]*true'; then
  if ! printf '%s' "$BACKUP_SAIDA" | grep -Eq '"offsite_ok"[[:space:]]*:[[:space:]]*true'; then
    log "ERRO CRÍTICO: política exige offsite e offsite_ok=true não foi comprovado."
    log "Deploy bloqueado antes de qualquer mutação de .env/imagens/runtime."
    exit 1
  fi
fi
else
  [ -n "$BACKUP_SAIDA" ] && printf '%s\n' "$BACKUP_SAIDA"
  if [ "$REQUIRE_PREDEPLOY_BACKUP" = "1" ]; then
    log "ERRO CRÍTICO: backup pré-deploy obrigatório falhou."
    log "Deploy bloqueado antes de qualquer mutação de .env/imagens/runtime."
    exit 1
  fi
  log "AVISO: backup pré-deploy não executou; contingência permissiva explícita seguirá sem prova nova."
fi

# Escopo frontend-only: mantém exatamente os mesmos gates anteriores
# (Woodpecker no wrapper, migration check, mutex, capacidade e backup cifrado),
# mas não toca .env, backend, worker, seeds, RAG ou prova pós-recreate do backup.
# Qualquer escopo ambíguo é classificado como "full" antes de chegar aqui.
deploy_frontend_only() {
  local old_image
  old_image="$(docker inspect -f '{{.Image}}' ejc_frontend 2>/dev/null || true)"
  FRONTEND_OLD_REF="$(docker inspect -f '{{.Config.Image}}' ejc_frontend 2>/dev/null || true)"
  [ -n "$old_image" ] && [ -n "$FRONTEND_OLD_REF" ] \
    || die_policy "frontend atual sem imagem/referência verificável; use deploy full"

  FRONTEND_ROLLBACK_TAG="ejc-frontend:rollback-${ROLLBACK_SUFFIX}"
  docker tag "$old_image" "$FRONTEND_ROLLBACK_TAG"

  log "Build frontend-only; backend, worker e RAG permanecem intocados"
  docker compose build frontend

  # A partir daqui o runtime é mutado. O trap precisa estar armado ANTES de
  # remover o container vivo para cobrir SIGINT/SIGTERM/SIGHUP e falha de compose.
  FRONTEND_ONLY_ROLLBACK_ARMED=1
  docker rm -f ejc_frontend >/dev/null 2>&1
  RUN_MIGRATIONS=0 docker compose up -d --no-deps --force-recreate frontend

  sleep 5
  curl -fsS --connect-timeout 5 --max-time 15 http://127.0.0.1:8080/ >/dev/null
  curl -fsS --connect-timeout 5 --max-time 15 "https://${DOMAIN}/" >/dev/null
  EJC_DOMAIN="$DOMAIN" bash scripts/post_deploy_check.sh

  # Identidade própria: o backend não foi recriado, portanto /api/health.commit
  # continua apontando corretamente para o SHA do backend. Não avançamos
  # .deployed_sha; registramos somente o artefato frontend publicado.
  printf '%s\n' "$GIT_SHA" > "$FRONTEND_DEPLOYED_SHA_TMP"
  chmod 600 "$FRONTEND_DEPLOYED_SHA_TMP"
  mv -f -- "$FRONTEND_DEPLOYED_SHA_TMP" "$APP_DIR/.frontend_deployed_sha"

  FRONTEND_ONLY_ROLLBACK_ARMED=0
  docker image rm "$FRONTEND_ROLLBACK_TAG" >/dev/null 2>&1 || true
  FRONTEND_ROLLBACK_TAG=""
  log "Deploy frontend-only concluído; backend/worker e identidade do backend permaneceram intactos."
}
if [ "$DEPLOY_SCOPE" = "frontend" ]; then
  deploy_frontend_only
  exit 0
fi

# Snapshot secreto efêmero, 0600, fora da árvore da aplicação e do diretório do
# mutex. `mktemp` cria O_EXCL; o trap remove em sucesso, falha e sinais tratados.
ENV_ROLLBACK_FILE="$(umask 077; mktemp /tmp/ejc-env-rollback.XXXXXX)" \
  || die_policy "não foi possível criar snapshot transacional temporário do .env"
cp -- .env "$ENV_ROLLBACK_FILE"
chmod 600 "$ENV_ROLLBACK_FILE"
ROLLBACK_ARMED=1

detect_env_immutable
ENV_MUTATED=1
unlock_env_if_needed

if [ -f scripts/migrar_env_obsoletos.sh ]; then
  bash scripts/migrar_env_obsoletos.sh .env --backup-path "$ENV_ROLLBACK_FILE" | while IFS= read -r linha; do
    log "$linha"
  done
fi

persist_git_sha_env
chmod 600 .env
relock_env_if_needed
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

# Preserva a imagem do runtime atual para rollback: reutiliza o image ID quando
# disponível e, se ele já tiver sido podado, materializa o container em execução.
snapshot_runtime_image() {
  local container="$1" image_id="$2" rollback_tag="$3" label="$4"
  if [ -n "$image_id" ] && docker image inspect "$image_id" >/dev/null 2>&1; then
    docker tag "$image_id" "$rollback_tag"
    return 0
  fi
  log "AVISO: image ID anterior de ${label} não está mais no catálogo local; preservando o container em execução como imagem de rollback."
  if docker commit "$container" "$rollback_tag" >/dev/null; then
    return 0
  fi
  if [ "$label" = "frontend" ]; then
    log "AVISO: docker commit do frontend falhou; usando export/import do filesystem com entrypoint/CMD canônicos do nginx."
    docker export "$container" | docker import \
      --change 'ENTRYPOINT ["/docker-entrypoint.sh"]' \
      --change 'CMD ["nginx","-g","daemon off;"]' \
      - "$rollback_tag" >/dev/null
    return 0
  fi
  return 1
}

if [ -n "$OLD_BACKEND_IMAGE" ]; then
  OLD_BACKEND_TAG="ejc-backend:rollback-${ROLLBACK_SUFFIX}"
  snapshot_runtime_image ejc_backend "$OLD_BACKEND_IMAGE" "$OLD_BACKEND_TAG" backend
fi
if [ -n "$OLD_WORKER_IMAGE" ]; then
  OLD_WORKER_TAG="ejc-worker:rollback-${ROLLBACK_SUFFIX}"
  snapshot_runtime_image ejc_worker "$OLD_WORKER_IMAGE" "$OLD_WORKER_TAG" worker
fi
if [ -n "$OLD_FRONTEND_IMAGE" ]; then
  OLD_FRONTEND_TAG="ejc-frontend:rollback-${ROLLBACK_SUFFIX}"
  snapshot_runtime_image ejc_frontend "$OLD_FRONTEND_IMAGE" "$OLD_FRONTEND_TAG" frontend
fi

OLD_GIT_SHA="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' \
  ejc_backend 2>/dev/null | sed -n 's/^GIT_SHA=//p' | head -1)"
log "Versão atualmente publicada: ${OLD_GIT_SHA:-indisponível}"

IMAGES_MUTATED=1
log "Build frontend"
docker compose build frontend
log "Build backend e worker"
docker compose build backend worker

if [ "$RUN_MIGRATIONS" = "1" ]; then
  log "Aplicando migration expand-only antes da troca da API"
  if [ -f "$MIGRATION_DATABASE_URL_FILE" ]; then
    migration_mode="$(stat -c '%a' "$MIGRATION_DATABASE_URL_FILE" 2>/dev/null || true)"
    case "$migration_mode" in
      400|600) ;;
      *) die_policy "arquivo da credencial de migration deve estar em modo 0400 ou 0600" ;;
    esac
    MIGRATION_DATABASE_URL="$(cat "$MIGRATION_DATABASE_URL_FILE")"
    [ -n "$MIGRATION_DATABASE_URL" ] || die_policy "arquivo da credencial de migration está vazio"
    export MIGRATION_DATABASE_URL
    docker compose run --rm --no-deps -T -e MIGRATION_DATABASE_URL backend alembic upgrade head
    unset MIGRATION_DATABASE_URL
  else
    log "AVISO: credencial dedicada de migration ainda não provisionada; usando fallback DATABASE_URL_SYNC somente neste container one-shot."
    docker compose run --rm --no-deps -T backend alembic upgrade head
  fi
else
  log "Nenhuma migration pendente; schema preservado."
fi

DEPLOY_MUTATED=1
log "Subindo backend novo sem migration automática no entrypoint"
RUN_MIGRATIONS=0 docker compose up -d --no-deps --force-recreate backend
connect_evolution_network_if_present ejc_backend
backend_ok=0
for _ in $(seq 1 12); do
  sleep 5
  if curl -fsS --connect-timeout 5 --max-time 15 http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    backend_ok=1
    break
  fi
done
[ "$backend_ok" = "1" ] || { log "Backend não respondeu em 60s"; exit 1; }

COMMIT_NO_AR="$(curl -fsS --connect-timeout 5 --max-time 15 http://127.0.0.1:8000/api/health 2>/dev/null \
  | sed -n 's/.*"commit"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
if [ "$COMMIT_NO_AR" = "$GIT_SHA" ]; then
  log "Versão publicada confirmada pelo /api/health: ${COMMIT_NO_AR}"
elif [ -z "$COMMIT_NO_AR" ] || [ "$COMMIT_NO_AR" = "desconhecido" ]; then
  log "ERRO CRÍTICO: /api/health respondeu sem a identidade do artefato (valor: '${COMMIT_NO_AR:-vazio}')."
  exit 1
else
  log "ERRO CRÍTICO: backend no ar declara ${COMMIT_NO_AR}, esperado ${GIT_SHA}."
  exit 1
fi

log "Atualizando worker"
RUN_MIGRATIONS=0 docker compose up -d --no-deps --force-recreate worker
connect_evolution_network_if_present ejc_worker

if [ "$ENSURE_DAILY_BACKUP" = "1" ]; then
  log "Garantindo agendamento e prova recente do backup cifrado"
  if bash scripts/backup/ativar_backup.sh; then
    log "Backup diário verificado com sucesso."
  else
    if [ "$REQUIRE_PREDEPLOY_BACKUP" = "1" ]; then
      log "ERRO CRÍTICO: ativação/verificação obrigatória do backup diário falhou."
      log "Deploy será revertido para preservar a política de continuidade."
      exit 1
    fi
    log "AVISO: ativação/verificação do backup diário falhou; contingência explícita mantém o deploy."
  fi
else
  log "AVISO CRÍTICO: ENSURE_DAILY_BACKUP=0 — garantia diária ignorada por contingência explícita."
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

printf '%s\n' "$GIT_SHA" > "$DEPLOYED_SHA_TMP"
chmod 644 "$DEPLOYED_SHA_TMP"
mv -f -- "$DEPLOYED_SHA_TMP" "$APP_DIR/.deployed_sha"
rm -f -- "$APP_DIR/.frontend_deployed_sha"
log "Versão implantada registrada atomicamente em .deployed_sha; marcador frontend parcial limpo."

ROLLBACK_ARMED=0
cleanup_temp_files
cleanup_rollback_tags
log "Deploy seguro concluído com sucesso."
