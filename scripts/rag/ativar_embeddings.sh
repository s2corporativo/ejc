#!/usr/bin/env bash
# EJC — ativação idempotente e reversível da busca semântica do RAG.
#
# Altera somente EMBEDDINGS_ENABLED. Provider, modelo e dimensão precisam estar
# previamente configurados como local + multilingual-e5-large + 1024d.
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/ejc}"
APP_CONTAINER="${APP_CONTAINER:-ejc_backend}"
WORKER_CONTAINER="${WORKER_CONTAINER:-ejc_worker}"
ENV_FILE="${ENV_FILE:-.env}"
RAG_CANARY_DOCS="${RAG_CANARY_DOCS:-5}"
RAG_REPORT_PATH="${RAG_REPORT_PATH:-}"
PROBE_SCRIPT="scripts/rag/provar_ativacao.py"

log() { printf '[ativar-rag] %s\n' "$*"; }
die() { printf '[ativar-rag] ERRO: %s\n' "$*" >&2; exit 1; }

case "$RAG_CANARY_DOCS" in
  ''|*[!0-9]*) die "RAG_CANARY_DOCS deve ser inteiro entre 1 e 50." ;;
esac
[ "$RAG_CANARY_DOCS" -ge 1 ] && [ "$RAG_CANARY_DOCS" -le 50 ] || \
  die "RAG_CANARY_DOCS deve ficar entre 1 e 50."

[ -d "$APP_DIR" ] || die "APP_DIR inexistente: $APP_DIR"
cd "$APP_DIR"
[ -f "$ENV_FILE" ] || die "$ENV_FILE não encontrado."
[ -f "$PROBE_SCRIPT" ] || die "$PROBE_SCRIPT não encontrado."
[ -f scripts/backup.sh ] || die "scripts/backup.sh não encontrado."
command -v docker >/dev/null 2>&1 || die "docker não encontrado."
docker exec "$APP_CONTAINER" true >/dev/null 2>&1 || \
  die "container $APP_CONTAINER não está no ar."

if docker compose version >/dev/null 2>&1; then
  DC=(docker compose)
else
  DC=(docker-compose)
fi

write_report() {
  local payload="$1"
  if [ -n "$RAG_REPORT_PATH" ]; then
    printf '%s\n' "$payload" > "$RAG_REPORT_PATH"
    chmod 600 "$RAG_REPORT_PATH" 2>/dev/null || true
  fi
}

get_env_var() {
  local key="$1"
  grep -E "^${key}=" "$ENV_FILE" 2>/dev/null \
    | tail -1 | cut -d= -f2- | tr -d "\"'\r" || true
}

set_env_var() {
  local key="$1" value="$2"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

wait_backend() {
  local backend_ok=0
  for _ in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1 || \
       docker exec "$APP_CONTAINER" \
         curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
      backend_ok=1
      break
    fi
    sleep 2
  done
  [ "$backend_ok" = "1" ]
}

ENV_BAK=""
ROLLBACK_ARMED=0

rollback_on_exit() {
  local rc=$?
  trap - EXIT INT TERM
  if [ "$ROLLBACK_ARMED" = "1" ] && [ -n "$ENV_BAK" ] && [ -f "$ENV_BAK" ]; then
    set +e
    log "falha detectada; restaurando a configuração anterior."
    cp "$ENV_BAK" "$ENV_FILE"
    chmod 600 "$ENV_FILE" 2>/dev/null || true
    "${DC[@]}" up -d --force-recreate --no-deps backend worker
    if wait_backend; then
      rm -f "$ENV_BAK"
      log "rollback confirmado e cópia transitória removida."
    else
      log "ALERTA: configuração restaurada, mas o health falhou; cópia preservada em $ENV_BAK."
    fi
  fi
  exit "$rc"
}

log "executando probe real 1024d antes de alterar produção..."
if PREFLIGHT_JSON="$(
  docker exec -e EMBEDDINGS_ENABLED=true -i "$APP_CONTAINER" \
    python - preflight < "$PROBE_SCRIPT"
)"; then
  printf '%s\n' "$PREFLIGHT_JSON"
else
  rc=$?
  write_report "$PREFLIGHT_JSON"
  die "preflight falhou (rc=$rc); nenhuma configuração foi alterada."
fi

log "exigindo backup cifrado completo antes da ativação..."
bash scripts/backup.sh

ENV_BAK="${ENV_FILE}.bak.rag.$(date +%Y%m%d_%H%M%S)"
cp "$ENV_FILE" "$ENV_BAK"
chmod 600 "$ENV_BAK" "$ENV_FILE" 2>/dev/null || true
ROLLBACK_ARMED=1
trap rollback_on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

PREVIOUS_ENABLED="$(get_env_var EMBEDDINGS_ENABLED)"
set_env_var EMBEDDINGS_ENABLED "true"
chmod 600 "$ENV_FILE" 2>/dev/null || true
log "EMBEDDINGS_ENABLED atualizado (valor anterior: ${PREVIOUS_ENABLED:-ausente})."

log "recriando backend e worker para carregar a configuração efetiva..."
"${DC[@]}" up -d --force-recreate --no-deps backend worker
wait_backend || die "backend não ficou saudável após a ativação."
[ "$(docker inspect -f '{{.State.Running}}' "$WORKER_CONTAINER" 2>/dev/null)" = "true" ] || \
  die "worker não ficou em execução após a ativação."

log "reindexando lote canário de até ${RAG_CANARY_DOCS} documento(s)..."
if CANARY_JSON="$(
  docker exec -i "$APP_CONTAINER" python - canary \
    --max-docs "$RAG_CANARY_DOCS" < "$PROBE_SCRIPT"
)"; then
  printf '%s\n' "$CANARY_JSON"
else
  rc=$?
  write_report "$CANARY_JSON"
  die "reindexação canário falhou (rc=$rc)."
fi

log "comprovando flag, provider, dimensão, cobertura e continuidade..."
if PROOF_JSON="$(
  docker exec -i "$APP_CONTAINER" python - proof < "$PROBE_SCRIPT"
)"; then
  printf '%s\n' "$PROOF_JSON"
else
  rc=$?
  write_report "$PROOF_JSON"
  die "prova final falhou (rc=$rc)."
fi

write_report "$PROOF_JSON"
ROLLBACK_ARMED=0
rm -f "$ENV_BAK"
trap - EXIT INT TERM

log "RAG semântico ATIVO; o scheduler concluirá os chunks vigentes pendentes."
