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
cp "$ROOT/scripts/migrar_env_obsoletos.sh" "$APP/scripts/migrar_env_obsoletos.sh"
: > "$APP/.env"

# Stub SOMENTE do fixture: o código produtivo não expõe override de caminho.
# Preserva a semântica relevante: FD 9 herdável + flock não bloqueante.
cat > "$APP/scripts/deploy_lock.sh" <<'EOF'
#!/usr/bin/env bash
ejc_deploy_lock_acquire() {
  local lock="${EJC_TEST_LOCK_FILE:?}" target
  mkdir -p "$(dirname "$lock")"
  [ -e "$lock" ] || : > "$lock"
  if [ -n "${EJC_DEPLOY_LOCK_FD:-}" ]; then
    [ "$EJC_DEPLOY_LOCK_FD" = "9" ] || return 2
    [ -e "/proc/$$/fd/9" ] || return 2
    target="$(readlink -f "/proc/$$/fd/9")" || return 2
    [ "$target" = "$(readlink -f "$lock")" ] || return 2
    flock -n 9 || return 75
    return 0
  fi
  exec 9>>"$lock" || return 2
  flock -n 9 || return 75
  EJC_DEPLOY_LOCK_FD=9
  export EJC_DEPLOY_LOCK_FD
}
EOF

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
  "EJC_TEST_LOCK_FILE=$LOCK"
  "PATH=$BIN:$PATH"
  "FAKE_DOCKER_LOG=$LOG"
  "EXPECTED_HEALTH_SHA=$TEST_SHA"
  "OLD_SHA_FOR_TEST=$OLD_SHA"
)

# 0) Lock ocupado bloqueia antes de APP_DIR/Docker/runtime.
exec 8>"$LOCK"
flock -n 8 || fail "não foi possível preparar lock do teste"
set +e
env APP_DIR="$TMP/inexistente" EJC_TEST_LOCK_FILE="$LOCK" \
  bash "$APP/scripts/deploy_vps_safe.sh" >"$TMP/lock.out" 2>"$TMP/lock.err"
lock_rc=$?
set -e
[ "$lock_rc" -eq 75 ] || fail "lock ocupado retornou rc=$lock_rc, esperado 75"
grep -q 'Outro deploy EJC já está em execução' "$TMP/lock.out" || fail "mensagem de lock ausente"
flock -u 8
exec 8>&-

# 0.1) Filho revalida FD 9 herdado sem deadlock nem bypass.
: > "$LOG"
set +e
(
  export EJC_TEST_LOCK_FILE="$LOCK"
  # shellcheck source=/dev/null
  source "$APP/scripts/deploy_lock.sh"
  ejc_deploy_lock_acquire || exit $?
  env "${COMMON_ENV[@]}" EJC_DEPLOY_LOCK_FD=9 FAIL_BACKUP=1 \
    TARGET_SHA="$TEST_SHA" ENSURE_DAILY_BACKUP=1 \
    bash "$APP/scripts/deploy_vps_safe.sh"
) >"$TMP/inherited.out" 2>"$TMP/inherited.err"
inherited_rc=$?
set -e
[ "$inherited_rc" -eq 1 ] || fail "filho com lock herdado retornou rc=$inherited_rc; esperava falha do backup"
grep -q 'backup pré-deploy obrigatório falhou' "$TMP/inherited.out" || fail "filho não chegou ao gate de backup"
! grep -q 'Outro deploy EJC já está em execução' "$TMP/inherited.out" || fail "lock herdado causou falso conflito"

# 0.2) Contrato REAL: um único namespace host-level, sem override por usuário/APP.
LOCK_SRC="$(cat "$ROOT/scripts/deploy_lock.sh")"
printf '%s' "$LOCK_SRC" | grep -q 'EJC_DEPLOY_PRODUCTION_LOCK_ROOT="/run/lock/ejc"' || fail "lock de produção não é fixo"
printf '%s' "$LOCK_SRC" | grep -q 'install -d -m 0750 -o root -g' || fail "raiz produtiva não é root-owned 0750"
printf '%s' "$LOCK_SRC" | grep -q '0660 -o root -g' || fail "arquivo produtivo não é root:docker 0660"
printf '%s' "$LOCK_SRC" | grep -q "stat -Lc '%d:%i'" || fail "helper não valida dev:inode"
printf '%s' "$LOCK_SRC" | grep -q 'inode mudou durante abertura' || fail "helper não fecha TOCTOU pós-open"
! printf '%s' "$LOCK_SRC" | grep -q 'XDG_RUNTIME_DIR' || fail "lock voltou a depender de XDG_RUNTIME_DIR"
! printf '%s' "$LOCK_SRC" | grep -q '\${HOME' || fail "lock voltou a depender de HOME"
! printf '%s' "$LOCK_SRC" | grep -q 'EJC_DEPLOY_LOCK_ROOT:-' || fail "lock produtivo voltou a aceitar override de raiz"
! printf '%s' "$LOCK_SRC" | grep -q 'app_canon' || fail "APP_DIR voltou a selecionar namespace de lock"

# 1) Migration incompatível falha antes de Docker.
: > "$LOG"
set +e
env "${COMMON_ENV[@]}" RUN_MIGRATIONS=1 ENSURE_DAILY_BACKUP=1 \
  bash "$APP/scripts/deploy_vps_safe.sh" >"$TMP/policy.out" 2>"$TMP/policy.err"
policy_rc=$?
set -e
[ "$policy_rc" -eq 2 ] || fail "política retornou rc=$policy_rc, esperado 2"
[ ! -s "$LOG" ] || fail "Docker foi chamado antes da política de migration"
grep -q "MIGRATIONS_BACKWARD_COMPATIBLE=1" "$TMP/policy.err" || fail "mensagem da política ausente"

# 2) Identidade inválida bloqueia antes de migrar .env ou chamar Docker.
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
[ ! -e "$TMP/env-migration-ran" ] || fail "migrador rodou antes de validar identidade"
[ ! -s "$LOG" ] || fail "Docker foi chamado antes de validar identidade"
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

# 4) Contingência exige opt-out explícito e registra a release sob o lock.
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

# 6) Migration expand-only precede backend; backend saudável precede worker.
: > "$LOG"
env "${COMMON_ENV[@]}" RUN_MIGRATIONS=1 MIGRATIONS_BACKWARD_COMPATIBLE=1 \
  TARGET_SHA="$TEST_SHA" RUN_SEEDS=0 ENSURE_DAILY_BACKUP=0 REQUIRE_PREDEPLOY_BACKUP=0 \
  bash "$APP/scripts/deploy_vps_safe.sh" >"$TMP/order.out" 2>"$TMP/order.err"
migration_line="$(grep -n '^compose run --rm --no-deps -T backend alembic upgrade head$' "$LOG" | cut -d: -f1)"
backend_line="$(grep -n '^compose up -d --no-deps --force-recreate backend$' "$LOG" | head -1 | cut -d: -f1)"
worker_line="$(grep -n '^compose up -d --no-deps --force-recreate worker$' "$LOG" | head -1 | cut -d: -f1)"
[ -n "$migration_line" ] && [ -n "$backend_line" ] && [ -n "$worker_line" ] || fail "ordem de deploy incompleta"
[ "$migration_line" -lt "$backend_line" ] || fail "backend foi trocado antes da migration"
[ "$backend_line" -lt "$worker_line" ] || fail "worker foi trocado antes do backend validado"

# 7) Falha de build restaura refs + .env, sem restart nem .env.bak persistente.
printf '%s\n' 'GROQ_MODEL=llama-3.3-70b-versatile' > "$APP/.env"
chmod 600 "$APP/.env"
ENV_ANTES="$(cat "$APP/.env")"
rm -f "$APP"/.env.bak.*
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
grep -Eq '^tag ejc-backend:rollback-.* project-backend:latest$' "$LOG" || fail "ref backend anterior não foi restaurada"
grep -Eq '^tag ejc-worker:rollback-.* project-worker:latest$' "$LOG" || fail "ref worker anterior não foi restaurada"
grep -Eq '^tag ejc-frontend:rollback-.* project-frontend:latest$' "$LOG" || fail "ref frontend anterior não foi restaurada"
! grep -q '^compose up -d --no-deps --force-recreate backend worker frontend$' "$LOG" || fail "runtime reiniciou apesar de falha pré-cutover"
[ ! -s "$POST_LOG" ] || fail "post-check de rollback rodou sem cutover"

# 8) Falha pós-cutover restaura imagens + runtime.
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

# 9) A entrada de deploy usa transação única e marcador de fase explícito.
# O gatilho deixou de ser o GitHub Actions (aposentado em #1533); o contrato
# vale sobre o mecanismo, não sobre o gatilho: quem dispara chama o wrapper
# transacional, e é o wrapper que marca cada fase.
ENTRADA="$ROOT/scripts/deploy_manual.sh"
TX="$ROOT/scripts/deploy_workflow_transaction.sh"
HOST_ENTRADA="$ROOT/infra/host-automation/ejc-deploy-approved.sh"
grep -q 'bash scripts/deploy_workflow_transaction.sh' "$ENTRADA" || fail "entrada de deploy não usa wrapper transacional"
grep -q 'write_phase sync_started' "$TX" || fail "wrapper não marca rsync parcial"
grep -q 'write_phase sync_completed' "$TX" || fail "wrapper não marca sync concluído"
grep -q 'write_phase deploy_completed' "$TX" || fail "wrapper não marca deploy concluído"
! grep -q 'SYNC_OUTCOME:' "$ENTRADA" "$TX" || fail "deploy ainda depende de outcome ambíguo"

# 10) Contratos de sintaxe e política.
grep -q 'REQUIRE_PREDEPLOY_BACKUP=1' "$ENTRADA" || fail "entrada de deploy não exige backup"
grep -q 'REQUIRE_PREDEPLOY_BACKUP=1' "$HOST_ENTRADA" || fail "automação do host não exige backup"
bash -n "$ROOT/scripts/deploy_lock.sh"
bash -n "$ROOT/scripts/deploy_workflow_transaction.sh"
bash -n "$ROOT/scripts/deploy_vps_safe.sh"
bash -n "$ROOT/scripts/migrar_env_obsoletos.sh"
echo "[rollback-test] OK — lock host-level/inode, backup fail-closed, env transacional, migration e rollback comprovados."
