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
DEPLOY="$ROOT/scripts/deploy_vps_safe.sh"
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

  # INF-04: `local_ok` agora significa persistência cifrada em BACKUP_DIR.
  # Offsite só é bloqueante quando a política o exige explicitamente.
  grep -q 'local_persisted' "$TMP/stdin.py" || fail "persistência local cifrada não é conferida"
  grep -q 'local_persistido' "$TMP/stdin.py" || fail "artefatos não comprovam persistência local"
  grep -q 'offsite_required = bool(config.get("offsite_obrigatorio"))' "$TMP/stdin.py" || \
    fail "política offsite não é lida"
  grep -q 'offsite_ok or not offsite_required' "$TMP/stdin.py" || \
    fail "gate não respeita política offsite após prova local persistente"
  grep -q 'artefatos_cifrados_persistidos' "$TMP/stdin.py" || \
    fail "saída não distingue persistência local"
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

# Integração do caller: local_ok=false sempre bloqueia. Quando a política
# declara offsite obrigatório, offsite_ok=false também bloqueia antes de mutar.
DEPLOY_CASE="$TMP/deploy-case"
DEPLOY_APP="$TMP/deploy-app"
mkdir -p "$DEPLOY_CASE" "$DEPLOY_APP/scripts"
cp "$DEPLOY" "$DEPLOY_CASE/deploy.sh"
cat > "$DEPLOY_CASE/deploy_lock.sh" <<'EOF'
ejc_deploy_lock_acquire() { return 0; }
EOF
cat > "$DEPLOY_APP/scripts/backup.sh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' '{"ok":true,"local_ok":false,"offsite_required":false,"offsite_ok":false,"destino":"rclone"}'
exit 0
EOF
chmod +x "$DEPLOY_APP/scripts/backup.sh"
: > "$DEPLOY_APP/.env"
: > "$DEPLOY_APP/docker-compose.yml"
: > "$TMP/deploy-docker.log"
set +e
PATH="$BIN:$PATH" \
FAKE_DOCKER_LOG="$TMP/deploy-docker.log" \
FAKE_STDIN_LOG="$TMP/deploy-stdin.py" \
APP_DIR="$DEPLOY_APP" \
TARGET_SHA="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" \
REQUIRE_PREDEPLOY_BACKUP=1 \
ENSURE_DAILY_BACKUP=1 \
bash "$DEPLOY_CASE/deploy.sh" >"$TMP/deploy-out" 2>"$TMP/deploy-err"
deploy_rc=$?
set -e
[ "$deploy_rc" -ne 0 ] || fail "deploy aceitou local_ok=false"
grep -q 'persistência local cifrada' "$TMP/deploy-out" || \
  fail "deploy não registrou bloqueio por local_ok ausente"
if grep -Eq '^compose build|^compose up|^tag ' "$TMP/deploy-docker.log"; then
  fail "deploy iniciou mutação de imagem/runtime após local_ok=false"
fi

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
python3 - "$DOCKERFILE" <<'PY_DOCKERFILE'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text()
blocks = re.findall(
    r"apt-get install -y.*?rm -rf /var/lib/apt/lists/\*",
    text,
    flags=re.S,
)
if not blocks:
    raise SystemExit("bloco apt-get install não encontrado")
token = re.compile(r"(?<![A-Za-z0-9_-])rclone(?![A-Za-z0-9_-])")
if any(token.search(block) for block in blocks):
    raise SystemExit("rclone voltou ao bloco apt-get install")
expected = r"RUN rclone version | grep -q '^rclone v1\.75\.0$'"
if expected not in text:
    raise SystemExit("assert de versão exata do rclone foi removido/alterado")
PY_DOCKERFILE

bash -n "$ROOT/scripts/backup.sh" "$DEPLOY" "$ACTIVATOR"
echo "[backup-wrapper-test] OK — pré-deploy exige persistência local cifrada e respeita política offsite."
