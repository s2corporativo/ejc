#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
cleanup_tmp() {
  set +e
  if [ -d "$TMP" ]; then
    find "$TMP" -depth -mindepth 1 -delete >/dev/null 2>&1 || true
    rmdir "$TMP" >/dev/null 2>&1 || true
  fi
}
trap cleanup_tmp EXIT

APP="$TMP/app"
BIN="$TMP/bin"
LOG="$TMP/docker.log"
POST_LOG="$TMP/post.log"
LOCK_ROOT="$TMP/locks"
LOCK="$LOCK_ROOT/deploy.lock"
TEST_SHA="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
OLD_SHA="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
mkdir -p "$APP/scripts/backup" "$BIN" "$LOCK_ROOT"
cp "$ROOT/scripts/deploy_vps_safe.sh" "$APP/scripts/deploy_vps_safe.sh"
cp "$ROOT/scripts/deploy_lock.sh" "$APP/scripts/deploy_lock.sh"
cp "$ROOT/scripts/migrar_env_obsoletos.sh" "$APP/scripts/migrar_env_obsoletos.sh"
: > "$APP/.env"

cat > "$APP/scripts/backup.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [ "${FAIL_BACKUP:-0}" = "1" ]; then
  echo backup-failed >&2
  exit 9
fi
echo '{"ok":true,"local_ok":true,"offsite_ok":true}'
EOF
cat > "$APP/scripts/backup/ativar_backup.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [ "${FAIL_DAILY_BACKUP:-0}" = "1" ]; then
  echo backup-daily-failed >&2
  exit 10
fi
echo backup-daily-ok
EOF
cat > "$APP/scripts/post_deploy_check.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
echo post-check >> "$POST_LOG"
EOF
chmod +x "$APP/scripts/"*.sh "$APP/scripts/backup/"*.sh

cat > "$BIN/docker" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "${FAKE_DOCKER_LOG:?}"

if [ "${1:-}" = "inspect" ]; then
  container="${*: -1}"
  if [[ "$*" == *"{{.Config.Image}}"* ]]; then
    case "$container" in
      ejc_backend) echo project-backend:latest ;;
      ejc_worker) echo project-worker:latest ;;
      ejc_frontend) echo project-frontend:latest ;;
    esac
  elif [[ "$*" == *"range .Config.Env"* ]]; then
    echo "GIT_SHA=${OLD_SHA_FOR_TEST:?}"
  else
    case "$container" in
      ejc_backend) echo sha256:backend-old ;;
      ejc_worker) echo sha256:worker-old ;;
      ejc_frontend) echo sha256:frontend-old ;;
    esac
  fi
  exit 0
fi

if [ "${1:-}" = "compose" ] && [ "${2:-}" = "build" ] && \
   [ "${3:-}" = "frontend" ] && [ "${FAIL_FRONTEND_BUILD:-0}" = "1" ]; then
  exit 42
fi

if [ "$*" = "compose up -d --no-deps --force-recreate worker" ] && \
   [ "${FAIL_WORKER_UPDATE:-0}" = "1" ]; then
  exit 43
fi

exit 0
EOF

cat > "$BIN/sleep" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
cat > "$BIN/curl" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "{\"status\":\"ok\",\"commit\":\"${EXPECTED_HEALTH_SHA:?}\"}"
EOF
chmod +x "$BIN/docker" "$BIN/sleep" "$BIN/curl"

fail() {
  echo "[rollback-test] FALHA: $*" >&2
  exit 1
}

COMMON_ENV=(
  "APP_DIR=$APP"
  "EJC_DEPLOY_LOCK_ROOT=$LOCK_ROOT"
  "EJC_DEPLOY_LOCK_FILE=$LOCK"
  "PATH=$BIN:$PATH"
  "FAKE_DOCKER_LOG=$LOG"
  "EXPECTED_HEALTH_SHA=$TEST_SHA"
  "OLD_SHA_FOR_TEST=$OLD_SHA"
)

# 0) Lock ocupado bloqueia antes de APP_DIR/Docker/runtime.
exec 8>"$LOCK"
flock -n 8 || fail "não foi possível preparar lock do teste"
set +e
env APP_DIR="$TMP/inexistente" EJC_DEPLOY_LOCK_ROOT="$LOCK_ROOT" \
  EJC_DEPLOY_LOCK_FILE="$LOCK" \
  bash "$ROOT/scripts/deploy_vps_safe.sh" >"$TMP/lock.out" 2>"$TMP/lock.err"
lock_rc=$?
set -e
[ "$lock_rc" -eq 75 ] || fail "lock ocupado retornou rc=$lock_rc, esperado 75"
grep -q 'Outro deploy EJC já está em execução' "$TMP/lock.out" || fail "mensagem de lock ausente"
flock -u 8
exec 8>&-

# 0.1) Lock sob APP_DIR é recusado antes de qualquer chamada Docker.
BAD_LOCK_ROOT="$APP/runtime-lock"
BAD_LOCK="$BAD_LOCK_ROOT/deploy.lock"
: > "$LOG"
set +e
env APP_DIR="$APP" EJC_DEPLOY_LOCK_ROOT="$BAD_LOCK_ROOT" EJC_DEPLOY_LOCK_FILE="$BAD_LOCK" \
  PATH="$BIN:$PATH" FAKE_DOCKER_LOG="$LOG" \
  bash "$APP/scripts/deploy_vps_safe.sh" >"$TMP/lock-path.out" 2>"$TMP/lock-path.err"
bad_lock_rc=$?
set -e
[ "$bad_lock_rc" -eq 2 ] || fail "lock sob APP_DIR retornou rc=$bad_lock_rc, esperado 2"
[ ! -s "$LOG" ] || fail "Docker foi chamado antes de rejeitar lock sob APP_DIR"
grep -q 'raiz do mutex deve ficar fora' "$TMP/lock-path.err" || fail "rejeição de lock sob APP_DIR não foi registrada"

# 0.2) Raiz de lock via symlink é recusada fail-closed.
LOCK_LINK="$TMP/locks-link"
ln -s "$LOCK_ROOT" "$LOCK_LINK"
: > "$LOG"
set +e
env APP_DIR="$APP" EJC_DEPLOY_LOCK_ROOT="$LOCK_LINK" \
  EJC_DEPLOY_LOCK_FILE="$LOCK_LINK/deploy-2.lock" PATH="$BIN:$PATH" FAKE_DOCKER_LOG="$LOG" \
  bash "$APP/scripts/deploy_vps_safe.sh" >"$TMP/lock-link.out" 2>"$TMP/lock-link.err"
lock_link_rc=$?
set -e
[ "$lock_link_rc" -eq 2 ] || fail "raiz symlink retornou rc=$lock_link_rc, esperado 2"
[ ! -s "$LOG" ] || fail "Docker foi chamado antes de rejeitar symlink do mutex"
grep -q 'EJC_DEPLOY_LOCK_ROOT não pode ser symlink' "$TMP/lock-link.err" || fail "rejeição de symlink não foi registrada"

# 0.3) Um processo filho pode REVALIDAR o FD 9 herdado sem deadlock/bypass.
: > "$LOG"
set +e
(
  export EJC_DEPLOY_LOCK_ROOT="$LOCK_ROOT" EJC_DEPLOY_LOCK_FILE="$LOCK"
  # shellcheck source=../deploy_lock.sh
  source "$APP/scripts/deploy_lock.sh"
  ejc_deploy_lock_acquire "$APP" || exit $?
  env "${COMMON_ENV[@]}" EJC_DEPLOY_LOCK_FD=9 FAIL_BACKUP=1 \
    TARGET_SHA="$TEST_SHA" ENSURE_DAILY_BACKUP=1 \
    bash "$APP/scripts/deploy_vps_safe.sh"
) >"$TMP/inherited.out" 2>"$TMP/inherited.err"
inherited_rc=$?
set -e
[ "$inherited_rc" -eq 1 ] || fail "filho com lock herdado retornou rc=$inherited_rc; esperava falha do backup"
grep -q 'backup pré-deploy obrigatório falhou' "$TMP/inherited.out" || fail "filho não chegou ao gate de backup com lock herdado"
! grep -q 'Outro deploy EJC já está em execução' "$TMP/inherited.out" || fail "lock herdado causou falso conflito"

# 0.4) Contrato de produção usa namespace único independente de HOME/XDG.
LOCK_SRC="$(cat "$ROOT/scripts/deploy_lock.sh")"
printf '%s' "$LOCK_SRC" | grep -q 'EJC_DEPLOY_PRODUCTION_LOCK_ROOT="/run/lock/ejc"' || fail "lock de produção não é host-level fixo"
printf '%s' "$LOCK_SRC" | grep -q 'install -d -m 0750 -o root -g' || fail "raiz de produção não é root-owned 0750"
printf '%s' "$LOCK_SRC" | grep -q '0660' || fail "arquivo de lock não é compartilhável pelo grupo do Docker"
! printf '%s' "$LOCK_SRC" | grep -q 'XDG_RUNTIME_DIR' || fail "lock de produção voltou a depender de XDG_RUNTIME_DIR"

# 1) Migration sem declaração de retrocompatibilidade falha antes de Docker.
: > "$LOG"
set +e
env "${COMMON_ENV[@]}" RUN_MIGRATIONS=1 ENSURE_DAILY_BACKUP=1 \
  bash "$APP/scripts/deploy_vps_safe.sh" >"$TMP/policy.out" 2>"$TMP/policy.err"
policy_rc=$?
set -e
[ "$policy_rc" -eq 2 ] || fail "política retornou rc=$policy_rc, esperado 2"
[ ! -s "$LOG" ] || fail "Docker foi chamado antes da política de migration"
grep -q "MIGRATIONS_BACKWARD_COMPATIBLE=1" "$TMP/policy.err" || fail "mensagem da política ausente"

# 2) Identidade inválida é bloqueada antes de migrar .env ou chamar Docker.
cp "$APP/scripts/migrar_env_obsoletos.sh" "$TMP/migrar-real.sh"
cat > "$APP/scripts/migrar_env_obsoletos.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
echo touched > "$TMP/env-migration-ran"
EOF
chmod +x "$APP/scripts/migrar_env_obsoletos.sh"
: > "$LOG"
set +e
env "${COMMON_ENV[@]}" TARGET_SHA=curto REQUIRE_PREDEPLOY_BACKUP=0 ENSURE_DAILY_BACKUP=0 \
  bash "$APP/scripts/deploy_vps_safe.sh" >"$TMP/sha-invalid.out" 2>"$TMP/sha-invalid.err"
sha_invalid_rc=$?
set -e
[ "$sha_invalid_rc" -eq 2 ] || fail "SHA inválido retornou rc=$sha_invalid_rc, esperado 2"
[ ! -e "$TMP/env-migration-ran" ] || fail "migrador de .env rodou antes de validar identidade"
[ ! -s "$LOG" ] || fail "Docker foi chamado antes de validar identidade"
grep -q 'SHA-1 completo de 40 caracteres' "$TMP/sha-invalid.err" || fail "mensagem de SHA inválido ausente"
mv "$TMP/migrar-real.sh" "$APP/scripts/migrar_env_obsoletos.sh"
chmod +x "$APP/scripts/migrar_env_obsoletos.sh"

# 3) Backup obrigatório falha antes de QUALQUER mutação persistente.
cat > "$APP/scripts/migrar_env_obsoletos.sh.stub" <<EOF
#!/usr/bin/env bash
set -euo pipefail
echo touched > "$TMP/env-migration-ran-after-backup"
EOF
chmod +x "$APP/scripts/migrar_env_obsoletos.sh.stub"
mv "$APP/scripts/migrar_env_obsoletos.sh" "$APP/scripts/migrar_env_obsoletos.sh.real"
mv "$APP/scripts/migrar_env_obsoletos.sh.stub" "$APP/scripts/migrar_env_obsoletos.sh"
rm -f "$TMP/env-migration-ran-after-backup"
: > "$LOG"
set +e
env "${COMMON_ENV[@]}" FAIL_BACKUP=1 TARGET_SHA="$TEST_SHA" ENSURE_DAILY_BACKUP=1 \
  bash "$APP/scripts/deploy_vps_safe.sh" >"$TMP/backup-default.out" 2>"$TMP/backup-default.err"
backup_default_rc=$?
set -e
[ "$backup_default_rc" -ne 0 ] || fail "default não bloqueou deploy sem backup"
[ ! -e "$TMP/env-migration-ran-after-backup" ] || fail "migrador alterou .env antes da aprovação do backup"
! grep -q '^tag ' "$LOG" || fail "docker tag ocorreu antes da aprovação do backup"
! grep -q '^compose build ' "$LOG" || fail "build iniciou após falha do backup"
! grep -q '^compose up ' "$LOG" || fail "runtime foi tocado após falha do backup"
grep -q 'backup pré-deploy obrigatório falhou' "$TMP/backup-default.out" || fail "fail-closed do backup não foi registrado"
rm "$APP/scripts/migrar_env_obsoletos.sh"
mv "$APP/scripts/migrar_env_obsoletos.sh.real" "$APP/scripts/migrar_env_obsoletos.sh"

# 4) Contingência exige opt-out explícito e fica visível no log.
: > "$LOG"
env "${COMMON_ENV[@]}" FAIL_BACKUP=1 REQUIRE_PREDEPLOY_BACKUP=0 \
  TARGET_SHA="$TEST_SHA" ENSURE_DAILY_BACKUP=0 \
  bash "$APP/scripts/deploy_vps_safe.sh" >"$TMP/backup-contingency.out" 2>"$TMP/backup-contingency.err"
grep -q '^compose build frontend$' "$LOG" || fail "contingência não prosseguiu para o build"
grep -q 'REQUIRE_PREDEPLOY_BACKUP=0 foi definido explicitamente' "$TMP/backup-contingency.out" || fail "contingência não ficou destacada"
[ "$(cat "$APP/.deployed_sha")" = "$TEST_SHA" ] || fail ".deployed_sha não foi registrado dentro do deploy"

# 5) Sem Git e sem TARGET_SHA, release é bloqueada antes de Docker.
: > "$LOG"
set +e
env "${COMMON_ENV[@]}" REQUIRE_PREDEPLOY_BACKUP=0 ENSURE_DAILY_BACKUP=0 \
  bash "$APP/scripts/deploy_vps_safe.sh" >"$TMP/sha.out" 2>"$TMP/sha.err"
sha_rc=$?
set -e
[ "$sha_rc" -eq 2 ] || fail "identidade ausente retornou rc=$sha_rc, esperado 2"
[ ! -s "$LOG" ] || fail "Docker foi chamado sem identidade de release"
grep -q 'SHA-1 completo de 40 caracteres' "$TMP/sha.err" || fail "mensagem de identidade ausente não apareceu"

# 6) Migration expand-only é aplicada antes da troca do backend.
: > "$LOG"
env "${COMMON_ENV[@]}" RUN_MIGRATIONS=1 MIGRATIONS_BACKWARD_COMPATIBLE=1 \
  TARGET_SHA="$TEST_SHA" RUN_SEEDS=0 ENSURE_DAILY_BACKUP=0 REQUIRE_PREDEPLOY_BACKUP=0 \
  bash "$APP/scripts/deploy_vps_safe.sh" >"$TMP/order.out" 2>"$TMP/order.err"
migration_line="$(grep -n '^compose run --rm --no-deps -T backend alembic upgrade head$' "$LOG" | cut -d: -f1)"
backend_line="$(grep -n '^compose up -d --no-deps --force-recreate backend$' "$LOG" | head -1 | cut -d: -f1)"
worker_line="$(grep -n '^compose up -d --no-deps --force-recreate worker$' "$LOG" | head -1 | cut -d: -f1)"
[ -n "$migration_line" ] || fail "migration efêmera não executada"
[ -n "$backend_line" ] || fail "backend novo não foi iniciado"
[ -n "$worker_line" ] || fail "worker novo não foi iniciado"
[ "$migration_line" -lt "$backend_line" ] || fail "backend foi trocado antes da migration expand-only"
[ "$backend_line" -lt "$worker_line" ] || fail "worker foi trocado antes da validação inicial do backend"

# 7) Falha de build restaura refs + .env, sem restart nem cópia persistente de segredo.
printf '%s\n' 'GROQ_MODEL=llama-3.3-70b-versatile' > "$APP/.env"
chmod 600 "$APP/.env"
ENV_ANTES="$(cat "$APP/.env")"
rm -f "$APP"/.env.bak.* "$LOCK_ROOT"/env.rollback.*
: > "$LOG"
: > "$POST_LOG"
set +e
env "${COMMON_ENV[@]}" FAIL_FRONTEND_BUILD=1 TARGET_SHA="$TEST_SHA" \
  ENSURE_DAILY_BACKUP=0 REQUIRE_PREDEPLOY_BACKUP=0 \
  bash "$APP/scripts/deploy_vps_safe.sh" >"$TMP/build-rollback.out" 2>"$TMP/build-rollback.err"
build_rc=$?
set -e
[ "$build_rc" -eq 42 ] || fail "falha de build retornou rc=$build_rc, esperado 42"
[ "$(cat "$APP/.env")" = "$ENV_ANTES" ] || fail ".env não foi restaurado após falha pré-cutover"
[ -z "$(find "$APP" -maxdepth 1 -name '.env.bak.*' -print -quit)" ] || fail "migrador deixou backup persistente de segredo"
[ -z "$(find "$LOCK_ROOT" -maxdepth 1 -name 'env.rollback.*' -print -quit)" ] || fail "snapshot transacional não foi removido após rollback"
grep -Eq '^tag ejc-backend:rollback-.* project-backend:latest$' "$LOG" || fail "ref backend anterior não foi restaurada"
grep -Eq '^tag ejc-worker:rollback-.* project-worker:latest$' "$LOG" || fail "ref worker anterior não foi restaurada"
grep -Eq '^tag ejc-frontend:rollback-.* project-frontend:latest$' "$LOG" || fail "ref frontend anterior não foi restaurada"
! grep -q '^compose up -d --no-deps --force-recreate backend worker frontend$' "$LOG" || fail "runtime reiniciou apesar de falha pré-cutover"
[ ! -s "$POST_LOG" ] || fail "post-check de rollback rodou sem cutover"
grep -q 'referências de imagem anteriores restauradas sem reiniciar containers' "$TMP/build-rollback.out" || fail "rollback sem downtime não foi registrado"

# 8) Falha pós-cutover restaura imagens + runtime + .env.
: > "$APP/.env"
chmod 600 "$APP/.env"
: > "$LOG"
: > "$POST_LOG"
set +e
env "${COMMON_ENV[@]}" FAIL_WORKER_UPDATE=1 TARGET_SHA="$TEST_SHA" \
  ENSURE_DAILY_BACKUP=0 REQUIRE_PREDEPLOY_BACKUP=0 \
  bash "$APP/scripts/deploy_vps_safe.sh" >"$TMP/runtime-rollback.out" 2>"$TMP/runtime-rollback.err"
runtime_rc=$?
set -e
[ "$runtime_rc" -eq 43 ] || fail "falha pós-cutover retornou rc=$runtime_rc, esperado 43"
grep -q '^compose up -d --no-deps --force-recreate backend worker frontend$' "$LOG" || fail "runtime anterior não foi recriado"
grep -q '^post-check$' "$POST_LOG" || fail "post-check do rollback não executou"
grep -q 'Rollback confirmado pelo post-deploy check' "$TMP/runtime-rollback.out" || fail "rollback de runtime não foi confirmado"

# 9) Workflow usa uma única transação para rsync + deploy e fase explícita.
WF="$ROOT/.github/workflows/deploy-vps.yml"
grep -q 'run: bash scripts/deploy_workflow_transaction.sh' "$WF" || fail "workflow não usa wrapper transacional"
grep -q 'sync_started' "$WF" || fail "resumo não reconhece rsync parcial"
grep -q 'sync_completed' "$WF" || fail "resumo não reconhece sync concluído"
grep -q 'deploy_completed' "$WF" || fail "resumo não reconhece deploy concluído"
! grep -q 'SYNC_OUTCOME:' "$WF" || fail "workflow ainda depende de outcome ambíguo do step"

# 10) Contratos de sintaxe e políticas explícitas.
grep -q 'REQUIRE_PREDEPLOY_BACKUP: "1"' "$WF" || fail "workflow não exige backup pré-deploy"
bash -n "$ROOT/scripts/deploy_lock.sh"
bash -n "$ROOT/scripts/deploy_workflow_transaction.sh"
bash -n "$ROOT/scripts/deploy_vps_safe.sh"
bash -n "$ROOT/scripts/migrar_env_obsoletos.sh"
echo "[rollback-test] OK — lock herdado/host-level, backup fail-closed, env transacional, migration e rollback comprovados."
