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
if [ "${1:-}" = "inspect" ] && [ "${2:-}" = "-f" ]; then
  printf '%s\n' "${FAKE_BACKEND_STATE:-running}"
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
  local expected="$1" fake_rc="$2" state="$3" expected_command="$4"
  : > "$LOG"
  : > "$TMP/stdin.py"
  set +e
  PATH="$BIN:$PATH" \
  FAKE_DOCKER_LOG="$LOG" \
  FAKE_STDIN_LOG="$TMP/stdin.py" \
  FAKE_BACKUP_RC="$fake_rc" \
  FAKE_BACKEND_STATE="$state" \
  APP_DIR="$APP" \
  APP_CONTAINER=ejc_backend \
  bash "$ROOT/scripts/backup.sh" >"$TMP/out" 2>"$TMP/err"
  local rc=$?
  set -e
  [ "$rc" -eq "$expected" ] || fail "rc=$rc, esperado $expected"
  grep -q '^inspect -f {{.State.Status}} ejc_backend$' "$LOG" || fail "estado do container não foi verificado"
  grep -q "$expected_command" "$LOG" || fail "runner esperado não foi chamado"
  grep -q 'from app.services import backup_service' "$TMP/stdin.py" || \
    fail "wrapper não delegou ao motor canônico"
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

  # P0 Staff: os `.enc` atuais nascem em TemporaryDirectory; portanto
  # `local_ok`/artefatos gerados NÃO provam retenção recuperável após retorno.
  # Pré-deploy só fica verde com offsite confirmado.
  grep -q 'encrypted_generated' "$TMP/stdin.py" || fail "produção dos artefatos cifrados não é conferida"
  grep -q 'offsite_ok = bool(result.get("offsite_ok"))' "$TMP/stdin.py" || \
    fail "prova offsite não é lida do resultado"
  grep -q 'and offsite_ok' "$TMP/stdin.py" || \
    fail "gate pré-deploy ainda pode aprovar sem retenção offsite"
  grep -q 'artefatos_cifrados_gerados' "$TMP/stdin.py" || \
    fail "saída não diferencia geração temporária de retenção offsite"
  if grep -q 'deploy prossegue com prova local\|BACKUP_OFFSITE_OBRIGATORIO' "$TMP/stdin.py"; then
    fail "wrapper ainda admite falso verde baseado em prova local temporária"
  fi
  grep -q '_db.dump.enc' "$TMP/stdin.py" || fail "artefato do banco não é exigido"
  grep -q '_uploads.tar.gz.enc' "$TMP/stdin.py" || fail "artefato de uploads não é exigido"
  if grep -q 'drive_file_id\|result.get("erro")' "$TMP/stdin.py"; then
    fail "saída do wrapper contém identificador ou erro operacional desnecessário"
  fi
}

run_case 0 0 running '^exec -i ejc_backend python -$'
run_case 1 1 running '^exec -i ejc_backend python -$'
run_case 0 0 restarting '^compose run --rm --no-deps -T backend python -$'
grep -q '^compose config$' "$LOG" || fail "compose não foi validado no fallback"
grep -q 'Backend indisponível para exec (estado: restarting)' "$TMP/err" || fail "fallback de restart loop não foi registrado"

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

DOCKERFILE="$ROOT/backend/Dockerfile"
grep -q '^FROM rclone/rclone:1.75.0 AS rclone_runtime$' "$DOCKERFILE" || \
  fail "runtime não fixa a versão homologada do rclone"
grep -q '^COPY --from=rclone_runtime /usr/local/bin/rclone /usr/local/bin/rclone$' "$DOCKERFILE" || \
  fail "binário oficial do rclone não é copiado para o backend"
if grep -Eq 'postgresql-client[[:space:]]+rclone' "$DOCKERFILE"; then
  fail "rclone voltou a depender do pacote apt defasado"
fi

bash -n "$ROOT/scripts/backup.sh" "$ACTIVATOR"
echo "[backup-wrapper-test] OK — pré-deploy exige cifragem + retenção offsite recuperável, sem falso local_ok."
