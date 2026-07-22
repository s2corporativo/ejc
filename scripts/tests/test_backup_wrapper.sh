#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
BIN="$TMP/bin"
LOG="$TMP/docker.log"
APP="$TMP/app"
ACTIVATOR="$ROOT/scripts/backup/ativar_backup.sh"
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
  grep -q "$expected_command" "$LOG" || fail "runner esperado não foi chamado"
  grep -q 'from app.services import backup_service' "$TMP/stdin.py" || \
    fail "wrapper não delegou ao módulo canônico backup_service"
  grep -q 'configuracao_status' "$TMP/stdin.py" || \
    fail "configuração não é validada antes do backup"
  grep -q 'credencial_dedicada_configurada' "$TMP/stdin.py" || \
    fail "identidade dedicada não é obrigatória"
  grep -q 'auth_mode == "inherit"' "$TMP/stdin.py" || \
    fail "modo inherit não é bloqueado"
  config_line="$(grep -n 'configuracao_status' "$TMP/stdin.py" | head -1 | cut -d: -f1)"
  execute_line="$(grep -n 'executar_backup' "$TMP/stdin.py" | head -1 | cut -d: -f1)"
  [ "$config_line" -lt "$execute_line" ] || \
    fail "backup é iniciado antes do gate de configuração"
  grep -q 'status.*sucesso' "$TMP/stdin.py" || fail "status integral não é exigido"
  grep -q '_db.dump.enc' "$TMP/stdin.py" || fail "artefato do banco não é exigido"
  grep -q '_uploads.tar.gz.enc' "$TMP/stdin.py" || fail "artefato de uploads não é exigido"
  if grep -q 'drive_file_id\|result.get("erro")' "$TMP/stdin.py"; then
    fail "saída do wrapper contém identificador ou erro operacional desnecessário"
  fi
}

run_case 0 0 1 '^exec -i ejc_backend python -$'
run_case 1 1 1 '^exec -i ejc_backend python -$'
run_case 0 0 0 '^compose run --rm --no-deps -T backend python -$'
grep -q '^compose config$' "$LOG" || fail "compose não foi validado no fallback"
grep -q 'Backend parado' "$TMP/err" || fail "fallback não foi registrado"

# Padrões executáveis do fluxo em claro são proibidos. Comentários explicativos
# não geram falso positivo.
if grep -Eq \
  '^[[:space:]]*rclone[[:space:]]|^[[:space:]]*docker exec .*pg_dump|ejc_db_.*sql\.gz|ejc_uploads_.*tar\.gz' \
  "$ROOT/scripts/backup.sh"; then
  fail "padrão de backup legado em claro reapareceu"
fi

# O ativador é fail-closed: nada de chave gerada na VPS, pasta embutida,
# credencial herdada ou despejo de logs potencialmente sensíveis na Action.
grep -q 'BACKUP_ENCRYPTION_KEY ausente' "$ACTIVATOR" || \
  fail "ativador não exige chave previamente custodiada"
grep -q 'credencial_dedicada_configurada' "$ACTIVATOR" || \
  fail "ativador não valida identidade dedicada no processo efetivo"
grep -q 'AUTH_MODE.*inherit\|auth_mode.*inherit' "$ACTIVATOR" || \
  fail "ativador não bloqueia inherit"
if grep -q 'Fernet.generate_key\|1HBh66E4NfZtz3V_Zdln7N_g2iFSoOE9c\|docker logs' "$ACTIVATOR"; then
  fail "ativador voltou a gerar segredo, embutir pasta ou publicar logs"
fi
if grep -q 'result.get("erro")\|drive_file_id' "$ACTIVATOR"; then
  fail "ativador publica erro operacional ou identificador do Drive"
fi

bash -n "$ROOT/scripts/backup.sh" "$ACTIVATOR"
echo "[backup-wrapper-test] OK — backup e ativação exigem criptografia e identidade dedicada, sem fallback inseguro."
