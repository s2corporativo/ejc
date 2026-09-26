#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/ejc}"
SOURCE_DIR="${EJC_SOURCE_DIR:-/opt/s2-automation/source/ejc}"
GATE="${WOODPECKER_GATE:-/opt/s2-automation/host/woodpecker-approved-sha.sh}"
REPO_FULL_NAME="s2corporativo/ejc"
POLICY_FILE=""
TARGET_SHA=""

log() { printf '[ejc-approved] %s\n' "$*"; }
fail() { printf '[ejc-approved] ERRO: %s\n' "$*" >&2; exit 2; }
cleanup() { [ -z "$POLICY_FILE" ] || rm -f -- "$POLICY_FILE"; }
trap cleanup EXIT

for cmd in git docker python3 rsync curl; do
  command -v "$cmd" >/dev/null 2>&1 || fail "$cmd ausente"
done
docker compose version >/dev/null 2>&1 || fail "Docker Compose ausente"
[ -x "$GATE" ] || fail "gate Woodpecker ausente: $GATE"
[ -d "$APP_DIR" ] || fail "diretorio de producao ausente: $APP_DIR"
[ -f "$APP_DIR/.env" ] || fail ".env de producao ausente"
[ "$(stat -c '%u:%a' "$APP_DIR/.env")" = "0:600" ] || fail "$APP_DIR/.env deve ser root:root 0600"
[ -d "$SOURCE_DIR/.git" ] || fail "checkout privado ausente em $SOURCE_DIR; provisione uma clone read-only com deploy key antes de habilitar o servico"

log "atualizando checkout operacional read-only"
git -C "$SOURCE_DIR" fetch --prune origin main
git -C "$SOURCE_DIR" checkout -f main
git -C "$SOURCE_DIR" reset --hard origin/main
git -C "$SOURCE_DIR" clean -fdx
TARGET_SHA="$(git -C "$SOURCE_DIR" rev-parse HEAD)"
[[ "$TARGET_SHA" =~ ^[0-9a-f]{40}$ ]] || fail "SHA alvo invalido"

DEPLOYED_SHA=""
FRONTEND_DEPLOYED_SHA=""
[ -f "$APP_DIR/.deployed_sha" ] && DEPLOYED_SHA="$(cat "$APP_DIR/.deployed_sha" 2>/dev/null || true)"
[ -f "$APP_DIR/.frontend_deployed_sha" ] && FRONTEND_DEPLOYED_SHA="$(cat "$APP_DIR/.frontend_deployed_sha" 2>/dev/null || true)"
if [ "$DEPLOYED_SHA" = "$TARGET_SHA" ] \
   && curl -fsS --connect-timeout 5 --max-time 15 http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
  log "runtime completo ja esta saudavel no SHA $TARGET_SHA; nada a fazer"
  exit 0
fi
if [ "$FRONTEND_DEPLOYED_SHA" = "$TARGET_SHA" ] \
   && curl -fsS --connect-timeout 5 --max-time 15 http://127.0.0.1:8000/api/health >/dev/null 2>&1 \
   && curl -fsS --connect-timeout 5 --max-time 15 https://ejc.depaulateixeira.adv.br/ >/dev/null 2>&1; then
  log "frontend ja esta publicado no SHA $TARGET_SHA; backend permanece na identidade própria"
  exit 0
fi

log "exigindo pipeline Woodpecker push/main verde para $TARGET_SHA"
"$GATE" "$REPO_FULL_NAME" "$TARGET_SHA"

[ -f "$SOURCE_DIR/scripts/check_migration_compatibility.py" ] || fail "checker de migration ausente no SHA aprovado"
[ -f "$SOURCE_DIR/scripts/deploy_lock.sh" ] || fail "deploy_lock.sh ausente no SHA aprovado"
[ -f "$SOURCE_DIR/scripts/deploy_vps_safe.sh" ] || fail "deploy_vps_safe.sh ausente no SHA aprovado"
[ -f "$SOURCE_DIR/scripts/classify_deploy_scope.py" ] || fail "classificador de escopo ausente no SHA aprovado"

# A partir daqui, decisao de migration, sincronizacao e cutover compartilham o
# mesmo mutex. Isso impede que outro deploy altere schema/runtime entre a leitura
# de alembic_version e a aplicacao da decisao calculada.
# shellcheck source=/dev/null
source "$SOURCE_DIR/scripts/deploy_lock.sh"
lock_rc=0
ejc_deploy_lock_acquire_production || lock_rc=$?
case "$lock_rc" in
  0) ;;
  75) fail "outro deploy EJC esta em andamento" ;;
  *) fail "nao foi possivel adquirir mutex host-level" ;;
esac

# Revalida o SHA depois de adquirir o mutex. Se main avancou enquanto esperava,
# o novo commit precisa passar pelo Woodpecker e esta execucao nao toca producao.
git -C "$SOURCE_DIR" fetch --prune origin main
LATEST_SHA="$(git -C "$SOURCE_DIR" rev-parse origin/main)"
[ "$LATEST_SHA" = "$TARGET_SHA" ] || fail "main mudou antes da decisao de migration; deploy abortado"

current_revisions="$({
  docker exec ejc_db sh -lc \
    'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atq -c "SELECT version_num FROM alembic_version ORDER BY version_num"'
} | tr -d '\r')"
revision_count="$(printf '%s\n' "$current_revisions" | sed '/^$/d' | wc -l | tr -d ' ')"
[ "$revision_count" = "1" ] || fail "producao deve possuir exatamente uma revisao Alembic; encontradas $revision_count"
current_revision="$(printf '%s\n' "$current_revisions" | sed '/^$/d' | head -1)"

POLICY_FILE="$(umask 077; mktemp /tmp/ejc-migration-policy.XXXXXX.json)" || fail "nao foi possivel criar policy temporaria"
set +e
python3 "$SOURCE_DIR/scripts/check_migration_compatibility.py" \
  --versions-dir "$SOURCE_DIR/backend/alembic/versions" \
  --current-revision "$current_revision" \
  --output "$POLICY_FILE"
policy_rc=$?
set -e
case "$policy_rc" in
  0) ;;
  1) fail "migration pendente nao e expand-only; deploy automatico bloqueado" ;;
  2) fail "grafo Alembic invalido ou revisao atual desconhecida" ;;
  *) fail "checker de migration terminou com rc=$policy_rc" ;;
esac

pending_count="$(python3 - "$POLICY_FILE" <<'PY'
import json, sys
with open(sys.argv[1], encoding='utf-8') as f:
    data = json.load(f)
print(int(data.get('pending_count', 0)))
PY
)"
[[ "$pending_count" =~ ^[0-9]+$ ]] || fail "pending_count invalido"
RUN_MIGRATIONS=0
MIGRATIONS_BACKWARD_COMPATIBLE=0
if [ "$pending_count" -gt 0 ]; then
  RUN_MIGRATIONS=1
  MIGRATIONS_BACKWARD_COMPATIBLE=1
fi
log "migration gate aprovado sob mutex: atual=$current_revision pendentes=$pending_count"

DEPLOY_SCOPE="full"
if [ "$RUN_MIGRATIONS" = "0" ] \
   && [ "${RUN_SEEDS:-0}" != "1" ] \
   && [[ "$DEPLOYED_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  DEPLOY_SCOPE="$(python3 "$SOURCE_DIR/scripts/classify_deploy_scope.py"     --repo "$SOURCE_DIR" --previous "$DEPLOYED_SHA" --target "$TARGET_SHA"     2>/dev/null || printf 'full')"
fi
case "$DEPLOY_SCOPE" in
  frontend|full) ;;
  *) DEPLOY_SCOPE="full" ;;
esac
log "escopo de deploy selecionado: $DEPLOY_SCOPE"

log "sincronizando somente o SHA aprovado sob mutex"
rsync -a --delete \
  --exclude '.git/' \
  --exclude '.env' --exclude '.env.*' \
  --exclude '.deployed_sha' --exclude '.deploy_last_sha' \
  --exclude '.frontend_deployed_sha' \
  --exclude 'uploads/' --exclude 'backups/' \
  --exclude 'logs/' --exclude 'data/' --exclude 'storage/' \
  --exclude 'secrets/' --exclude 'certs/' --exclude 'tmp/' \
  --exclude 'node_modules/' --exclude 'frontend/node_modules/' \
  --exclude 'frontend/dist/' --exclude 'graphify-out/' \
  --exclude 'vps-tools/' --exclude '*.log' \
  "$SOURCE_DIR/" "$APP_DIR/"

# Revalida main ainda sob o mutex e antes do build/cutover.
git -C "$SOURCE_DIR" fetch --prune origin main
LATEST_SHA="$(git -C "$SOURCE_DIR" rev-parse origin/main)"
[ "$LATEST_SHA" = "$TARGET_SHA" ] || fail "main mudou durante a sincronizacao; runtime nao sera trocado"

log "executando deploy transacional existente"
cd "$APP_DIR"
TARGET_SHA="$TARGET_SHA" \
DEPLOY_SCOPE="$DEPLOY_SCOPE" \
RUN_MIGRATIONS="$RUN_MIGRATIONS" \
MIGRATIONS_BACKWARD_COMPATIBLE="$MIGRATIONS_BACKWARD_COMPATIBLE" \
RUN_SEEDS="${RUN_SEEDS:-0}" \
REQUIRE_PREDEPLOY_BACKUP=1 \
ENSURE_DAILY_BACKUP=1 \
bash scripts/deploy_vps_safe.sh

curl -fsS --connect-timeout 5 --max-time 15 http://127.0.0.1:8000/api/health >/dev/null
curl -fsS --connect-timeout 5 --max-time 15 https://ejc.depaulateixeira.adv.br/api/health >/dev/null
if [ "$DEPLOY_SCOPE" = "full" ]; then
  printf '%s\n' "$TARGET_SHA" > "$APP_DIR/.deploy_last_sha"
  chmod 600 "$APP_DIR/.deploy_last_sha"
  rm -f -- "$APP_DIR/.frontend_deployed_sha"
  log "deploy full concluido e identidade completa confirmada: $TARGET_SHA"
else
  [ -f "$APP_DIR/.frontend_deployed_sha" ] \
    && [ "$(cat "$APP_DIR/.frontend_deployed_sha")" = "$TARGET_SHA" ] \
    || fail "frontend-only terminou sem marcador de identidade correspondente"
  log "deploy frontend-only concluido e health local/publico confirmados: $TARGET_SHA"
fi
