#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
BIN="$TMP/bin"
LOG="$TMP/docker.log"
APP="$TMP/app"
mkdir -p "$BIN" "$APP"
: > "$APP/docker-compose.yml"

cat > "$BIN/docker" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "${FAKE_DOCKER_LOG:?}"
if [ "${1:-}" = "ps" ]; then
  if [ "${FAKE_BACKEND_RUNNING:-1}" = "1" ]; then
    echo ejc_backend
  fi
  exit 0
fi
if [ "${1:-}" = "exec" ]; then
  program="$(cat)"
  printf '%s' "$program" > "${FAKE_STDIN_LOG:?}"
  exit "${FAKE_BACKUP_RC:-0}"
fi
if [ "${1:-}" = "compose" ] && [ "${2:-}" = "config" ]; then
  exit 0
fi
if [ "${1:-}" = "compose" ] && [ "${2:-}" = "run" ]; then
  program="$(cat)"
  printf '%s' "$program" > "${FAKE_STDIN_LOG:?}"
  exit "${FAKE_BACKUP_RC:-0}"
fi
exit 0
EOF
chmod +x "$BIN/docker"

fail() {
  echo "[backup-wrapper-test] FALHA: $*" >&2
  exit 1
}

run_case() {
  local expected="$1" fake_rc="$2" running="$3" expected_command="$4"
  : > "$LOG"
  : > "$TMP/stdin.py"
  set +e
  PATH="$BIN:$PATH" \
  FAKE_DOCKER_LOG="$LOG" \
  FAKE_STDIN_LOG="$TMP/stdin.py" \
  FAKE_BACKUP_RC="$fake_rc" \
  FAKE_BACKEND_RUNNING="$running" \
  APP_DIR="$APP" \
  APP_CONTAINER=ejc_backend \
  bash "$ROOT/scripts/backup.sh" >"$TMP/out" 2>"$TMP/err"
  local rc=$?
  set -e
  [ "$rc" -eq "$expected" ] || fail "rc=$rc, esperado $expected"
  grep -q '^ps --format {{.Names}}$' "$LOG" || fail "container não foi verificado"
  grep -q "$expected_command" "$LOG" || fail "runner esperado não foi chamado: $expected_command"
  grep -q 'from app.services.backup_service import executar_backup' "$TMP/stdin.py" || \
    fail "wrapper não chamou backup_service.executar_backup"
  grep -q 'status.*sucesso' "$TMP/stdin.py" || fail "status integral não é exigido"
}

# Container saudável: reutiliza o processo já carregado.
run_case 0 0 1 '^exec -i ejc_backend python -$'
run_case 1 1 1 '^exec -i ejc_backend python -$'

# Backend parado/crash-loop: usa imagem anterior em container efêmero, mantendo
# env_file e volumes para banco/uploads sem bloquear o deploy corretivo.
run_case 0 0 0 '^compose run --rm --no-deps -T backend python -$'
grep -q '^compose config$' "$LOG" || fail "compose não foi validado no fallback"
grep -q 'Backend parado' "$TMP/err" || fail "fallback não foi registrado"

# Guardas estáticos: somente padrões executáveis são proibidos; comentários que
# documentam a remoção do fluxo antigo não geram falso positivo.
if grep -Eq \
  '^[[:space:]]*rclone[[:space:]]|pg_dump[[:space:]].*\|[[:space:]]*gzip|ejc_db_.*sql\.gz|ejc_uploads_.*tar\.gz' \
  "$ROOT/scripts/backup.sh"; then
  fail "padrão de backup legado em claro reapareceu"
fi

grep -q 'docker exec -i' "$ROOT/scripts/backup.sh" || fail "execução por STDIN ausente"
grep -q 'docker compose run --rm --no-deps -T backend python -' "$ROOT/scripts/backup.sh" || \
  fail "fallback efêmero ausente"
bash -n "$ROOT/scripts/backup.sh"

echo "[backup-wrapper-test] OK — serviço cifrado funciona com backend saudável ou parado."
