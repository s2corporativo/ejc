#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
BIN="$TMP/bin"
LOG="$TMP/docker.log"
mkdir -p "$BIN"

cat > "$BIN/docker" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "${FAKE_DOCKER_LOG:?}"
if [ "${1:-}" = "ps" ]; then
  echo ejc_backend
  exit 0
fi
if [ "${1:-}" = "exec" ]; then
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
  local expected="$1" fake_rc="$2"
  : > "$LOG"
  : > "$TMP/stdin.py"
  set +e
  PATH="$BIN:$PATH" \
  FAKE_DOCKER_LOG="$LOG" \
  FAKE_STDIN_LOG="$TMP/stdin.py" \
  FAKE_BACKUP_RC="$fake_rc" \
  APP_CONTAINER=ejc_backend \
  bash "$ROOT/scripts/backup.sh" >"$TMP/out" 2>"$TMP/err"
  local rc=$?
  set -e
  [ "$rc" -eq "$expected" ] || fail "rc=$rc, esperado $expected"
  grep -q '^ps --format {{.Names}}$' "$LOG" || fail "container não foi verificado"
  grep -q '^exec -i ejc_backend python -$' "$LOG" || fail "serviço nativo não foi chamado"
  grep -q 'from app.services.backup_service import executar_backup' "$TMP/stdin.py" || \
    fail "wrapper não chamou backup_service.executar_backup"
  grep -q 'status.*sucesso' "$TMP/stdin.py" || fail "status integral não é exigido"
}

run_case 0 0
run_case 1 1

# Guardas estáticos: somente padrões executáveis são proibidos; comentários que
# documentam a remoção do fluxo antigo não geram falso positivo.
if grep -Eq \
  '^[[:space:]]*rclone[[:space:]]|pg_dump[[:space:]].*\|[[:space:]]*gzip|ejc_db_.*sql\.gz|ejc_uploads_.*tar\.gz' \
  "$ROOT/scripts/backup.sh"; then
  fail "padrão de backup legado em claro reapareceu"
fi

grep -q 'docker exec -i' "$ROOT/scripts/backup.sh" || fail "execução por STDIN ausente"
bash -n "$ROOT/scripts/backup.sh"

echo "[backup-wrapper-test] OK — somente serviço nativo cifrado é utilizado."
