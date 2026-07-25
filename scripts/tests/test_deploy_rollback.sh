#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

APP="$TMP/app"
BIN="$TMP/bin"
LOG="$TMP/docker.log"
POST_LOG="$TMP/post.log"
mkdir -p "$APP/scripts/backup" "$BIN"
cp "$ROOT/scripts/deploy_vps_safe.sh" "$APP/scripts/deploy_vps_safe.sh"
: > "$APP/.env"

cat > "$APP/scripts/backup.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [ "${FAIL_BACKUP:-0}" = "1" ]; then
  echo backup-failed >&2
  exit 9
fi
echo backup-ok
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

exit 0
EOF

cat > "$BIN/sleep" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
cat > "$BIN/curl" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$BIN/docker" "$BIN/sleep" "$BIN/curl"

fail() {
  echo "[rollback-test] FALHA: $*" >&2
  exit 1
}

# 1) Migration sem declaração de retrocompatibilidade falha antes de Docker.
: > "$LOG"
set +e
APP_DIR="$APP" PATH="$BIN:$PATH" FAKE_DOCKER_LOG="$LOG" \
RUN_MIGRATIONS=1 ENSURE_DAILY_BACKUP=0 \
bash "$APP/scripts/deploy_vps_safe.sh" >"$TMP/policy.out" 2>"$TMP/policy.err"
policy_rc=$?
set -e
[ "$policy_rc" -eq 2 ] || fail "política retornou rc=$policy_rc, esperado 2"
[ ! -s "$LOG" ] || fail "Docker foi chamado antes da política de migration"
grep -q "MIGRATIONS_BACKWARD_COMPATIBLE=1" "$TMP/policy.err" || \
  fail "mensagem da política ausente"

# 2) Backup obrigatório falha fechado antes de qualquer build/mutação do runtime.
: > "$LOG"
set +e
APP_DIR="$APP" PATH="$BIN:$PATH" FAKE_DOCKER_LOG="$LOG" \
FAIL_BACKUP=1 REQUIRE_PREDEPLOY_BACKUP=1 ENSURE_DAILY_BACKUP=0 \
bash "$APP/scripts/deploy_vps_safe.sh" >"$TMP/backup-strict.out" 2>"$TMP/backup-strict.err"
backup_strict_rc=$?
set -e
[ "$backup_strict_rc" -ne 0 ] || fail "backup obrigatório não bloqueou o deploy"
! grep -q '^compose build ' "$LOG" || fail "build iniciou após falha de backup obrigatório"
grep -q 'backup pré-deploy obrigatório falhou' "$TMP/backup-strict.out" || \
  fail "mensagem fail-closed do backup ausente"
grep -q 'Falha antes de qualquer mutação do runtime' "$TMP/backup-strict.out" || \
  fail "não foi comprovado que o runtime permaneceu intacto"

# 3) Modo de contingência explícito continua permitindo deploy sem backup novo.
: > "$LOG"
APP_DIR="$APP" PATH="$BIN:$PATH" FAKE_DOCKER_LOG="$LOG" \
FAIL_BACKUP=1 REQUIRE_PREDEPLOY_BACKUP=0 ENSURE_DAILY_BACKUP=0 \
bash "$APP/scripts/deploy_vps_safe.sh" >"$TMP/backup-contingency.out" 2>"$TMP/backup-contingency.err"
grep -q '^compose build frontend$' "$LOG" || fail "contingência não prosseguiu para o build"
grep -q 'modo de contingência permissivo' "$TMP/backup-contingency.out" || \
  fail "contingência não ficou explicitamente registrada"

# 4) Migration expand-only é aplicada antes da troca do backend.
: > "$LOG"
APP_DIR="$APP" PATH="$BIN:$PATH" FAKE_DOCKER_LOG="$LOG" \
RUN_MIGRATIONS=1 MIGRATIONS_BACKWARD_COMPATIBLE=1 \
RUN_SEEDS=0 ENSURE_DAILY_BACKUP=0 REQUIRE_PREDEPLOY_BACKUP=0 \
bash "$APP/scripts/deploy_vps_safe.sh" >"$TMP/order.out" 2>"$TMP/order.err"

migration_line="$(grep -n '^compose run --rm --no-deps -T backend alembic upgrade head$' "$LOG" | cut -d: -f1)"
backend_line="$(grep -n '^compose up -d --no-deps --force-recreate backend$' "$LOG" | head -1 | cut -d: -f1)"
worker_line="$(grep -n '^compose up -d --no-deps --force-recreate worker$' "$LOG" | head -1 | cut -d: -f1)"
[ -n "$migration_line" ] || fail "migration efêmera não executada"
[ -n "$backend_line" ] || fail "backend novo não foi iniciado"
[ -n "$worker_line" ] || fail "worker novo não foi iniciado"
[ "$migration_line" -lt "$backend_line" ] || \
  fail "backend foi trocado antes da migration expand-only"
[ "$backend_line" -lt "$worker_line" ] || \
  fail "worker foi trocado antes da validação inicial do backend"

# 5) Falha de build restaura as três imagens anteriores e valida o rollback.
: > "$LOG"
: > "$POST_LOG"
set +e
APP_DIR="$APP" PATH="$BIN:$PATH" FAKE_DOCKER_LOG="$LOG" \
FAIL_FRONTEND_BUILD=1 ENSURE_DAILY_BACKUP=0 REQUIRE_PREDEPLOY_BACKUP=0 \
bash "$APP/scripts/deploy_vps_safe.sh" >"$TMP/rollback.out" 2>"$TMP/rollback.err"
rollback_rc=$?
set -e
[ "$rollback_rc" -eq 42 ] || fail "rollback retornou rc=$rollback_rc, esperado 42"

grep -Eq '^tag sha256:backend-old ejc-backend:rollback-' "$LOG" || \
  fail "tag imutável do backend anterior não foi criada"
grep -Eq '^tag sha256:worker-old ejc-worker:rollback-' "$LOG" || \
  fail "tag imutável do worker anterior não foi criada"
grep -Eq '^tag sha256:frontend-old ejc-frontend:rollback-' "$LOG" || \
  fail "tag imutável do frontend anterior não foi criada"

grep -Eq '^tag ejc-backend:rollback-.* project-backend:latest$' "$LOG" || \
  fail "backend anterior não foi restaurado na referência real"
grep -Eq '^tag ejc-worker:rollback-.* project-worker:latest$' "$LOG" || \
  fail "worker anterior não foi restaurado na referência real"
grep -Eq '^tag ejc-frontend:rollback-.* project-frontend:latest$' "$LOG" || \
  fail "frontend anterior não foi restaurado na referência real"

grep -q '^compose up -d --no-deps --force-recreate backend worker frontend$' "$LOG" || \
  fail "serviços não foram recriados no rollback"
grep -q '^post-check$' "$POST_LOG" || fail "post-check do rollback não executou"
grep -q 'Rollback confirmado pelo post-deploy check' "$TMP/rollback.out" || \
  fail "rollback não registrou confirmação"
grep -q 'Tags de rollback preservadas' "$TMP/rollback.out" || \
  fail "tags forenses não foram preservadas"

# 6) O workflow de produção ativa explicitamente a política fail-closed.
grep -q 'REQUIRE_PREDEPLOY_BACKUP: "1"' "$ROOT/.github/workflows/deploy-vps.yml" || \
  fail "workflow de produção não exige backup pré-deploy"
grep -q 'REQUIRE_PREDEPLOY_BACKUP="$REQUIRE_PREDEPLOY_BACKUP"' \
  "$ROOT/.github/workflows/deploy-vps.yml" || \
  fail "workflow não repassa a política ao script"

bash -n "$ROOT/scripts/deploy_vps_safe.sh"
echo "[rollback-test] OK — backup fail-closed, migration anterior à troca e rollback de backend/worker/frontend comprovados."
