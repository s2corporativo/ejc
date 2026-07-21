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
echo backup-ok
EOF
cat > "$APP/scripts/backup/ativar_backup.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
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
  case "${*: -1}" in
    ejc_backend) echo sha256:backend-old ;;
    ejc_frontend) echo sha256:frontend-old ;;
  esac
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

# 1) Migration sem declaração de retrocompatibilidade deve falhar ANTES de Docker.
: > "$LOG"
set +e
APP_DIR="$APP" \
PATH="$BIN:$PATH" \
FAKE_DOCKER_LOG="$LOG" \
RUN_MIGRATIONS=1 \
ENSURE_DAILY_BACKUP=0 \
bash "$APP/scripts/deploy_vps_safe.sh" >"$TMP/policy.out" 2>"$TMP/policy.err"
policy_rc=$?
set -e
[ "$policy_rc" -eq 2 ] || fail "política de migration retornou rc=$policy_rc, esperado 2"
[ ! -s "$LOG" ] || fail "Docker foi chamado antes da validação de migration"
grep -q "MIGRATIONS_BACKWARD_COMPATIBLE=1" "$TMP/policy.err" || \
  fail "mensagem de política de migration ausente"

# 2) Falha de build deve restaurar as imagens anteriores e validar o rollback.
: > "$LOG"
: > "$POST_LOG"
set +e
APP_DIR="$APP" \
PATH="$BIN:$PATH" \
FAKE_DOCKER_LOG="$LOG" \
FAIL_FRONTEND_BUILD=1 \
ENSURE_DAILY_BACKUP=0 \
bash "$APP/scripts/deploy_vps_safe.sh" >"$TMP/rollback.out" 2>"$TMP/rollback.err"
rollback_rc=$?
set -e
[ "$rollback_rc" -eq 42 ] || fail "rollback retornou rc=$rollback_rc, esperado 42"

grep -Eq '^tag sha256:backend-old ejc-backend:rollback-' "$LOG" || \
  fail "tag imutável do backend anterior não foi criada"
grep -Eq '^tag sha256:frontend-old ejc-frontend:rollback-' "$LOG" || \
  fail "tag imutável do frontend anterior não foi criada"
grep -Eq '^tag ejc-backend:rollback-.* ejc-backend:latest$' "$LOG" || \
  fail "backend anterior não foi restaurado para latest"
grep -Eq '^tag ejc-frontend:rollback-.* ejc-frontend:latest$' "$LOG" || \
  fail "frontend anterior não foi restaurado para latest"
grep -q '^compose up -d --no-deps backend worker frontend$' "$LOG" || \
  fail "serviços não foram recriados durante o rollback"
grep -q '^post-check$' "$POST_LOG" || fail "post-deploy check do rollback não executou"
grep -q 'Rollback confirmado pelo post-deploy check' "$TMP/rollback.out" || \
  fail "rollback não registrou confirmação"

# 3) Sintaxe sempre bloqueante.
bash -n "$ROOT/scripts/deploy_vps_safe.sh"

echo "[rollback-test] OK — política de migration e rollback de imagens comprovados."
