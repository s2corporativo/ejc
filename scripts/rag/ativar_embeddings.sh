#!/usr/bin/env bash
# EJC — ativação idempotente, auditável e reversível da busca semântica do RAG.
# Altera exclusivamente EMBEDDINGS_ENABLED no .env. Provider, modelo, dimensão,
# backup, runtime, canário governado e continuidade são comprovados.
set -Eeuo pipefail
umask 077

APP_DIR="${APP_DIR:-/opt/ejc}"
APP_CONTAINER="${APP_CONTAINER:-ejc_backend}"
WORKER_CONTAINER="${WORKER_CONTAINER:-ejc_worker}"
ENV_FILE="${ENV_FILE:-.env}"
RAG_CANARY_DOCS="${RAG_CANARY_DOCS:-5}"
RAG_REPORT_PATH="${RAG_REPORT_PATH:-}"
EXPECTED_GIT_SHA="${EXPECTED_GIT_SHA:-}"
PUBLIC_HEALTH_URL="${PUBLIC_HEALTH_URL:-https://ejc.depaulateixeira.adv.br/api/health}"
RAG_LOCK_FILE="${RAG_LOCK_FILE:-/tmp/ejc-rag-activation.lock}"
PROBE_SCRIPT="scripts/rag/provar_ativacao.py"
TMP_PARENT="${TMPDIR:-/tmp}"
TMP_DIR=""

log() { printf '[ativar-rag] %s\n' "$*"; }
die() { printf '[ativar-rag] ERRO: %s\n' "$*" >&2; exit 1; }

case "$RAG_CANARY_DOCS" in
  ''|*[!0-9]*) die "RAG_CANARY_DOCS deve ser inteiro entre 1 e 50." ;;
esac
[ "$RAG_CANARY_DOCS" -ge 1 ] && [ "$RAG_CANARY_DOCS" -le 50 ] || \
  die "RAG_CANARY_DOCS deve ficar entre 1 e 50."

for command_name in docker curl python3 flock sha256sum stat mktemp find rmdir dirname basename; do
  command -v "$command_name" >/dev/null 2>&1 || die "$command_name não encontrado."
done
[ -n "$EXPECTED_GIT_SHA" ] || die "EXPECTED_GIT_SHA é obrigatório."
[ -d "$APP_DIR" ] || die "APP_DIR inexistente: $APP_DIR"
[ -d "$TMP_PARENT" ] || die "diretório temporário inexistente: $TMP_PARENT"
cd "$APP_DIR"
[ -f "$ENV_FILE" ] || die "$ENV_FILE não encontrado."
[ -f "$PROBE_SCRIPT" ] || die "$PROBE_SCRIPT não encontrado."
[ -f scripts/backup.sh ] || die "scripts/backup.sh não encontrado."

exec 9>"$RAG_LOCK_FILE"
flock -n 9 || die "outra ativação do RAG já está em execução."

if docker compose version >/dev/null 2>&1; then
  DC=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  DC=(docker-compose)
else
  die "Docker Compose não encontrado."
fi
"${DC[@]}" config --quiet

docker exec "$APP_CONTAINER" true >/dev/null 2>&1 || \
  die "container $APP_CONTAINER não está no ar."
docker exec "$WORKER_CONTAINER" true >/dev/null 2>&1 || \
  die "container $WORKER_CONTAINER não está no ar."

TMP_DIR="$(mktemp -d "$TMP_PARENT/ejc-rag-activation.XXXXXXXX")"
RUNTIME_BACKEND_JSON="$TMP_DIR/runtime-backend.json"
RUNTIME_WORKER_JSON="$TMP_DIR/runtime-worker.json"
PREFLIGHT_JSON_FILE="$TMP_DIR/preflight.json"
BACKUP_JSON_FILE="$TMP_DIR/backup.json"
CANARY_JSON_FILE="$TMP_DIR/canary.json"
PREPROOF_JSON_FILE="$TMP_DIR/proof-before-scheduler.json"
PROOF_JSON_FILE="$TMP_DIR/proof.json"
LAST_JSON_FILE=""
ENV_BAK=""
ENV_SHA_BEFORE=""
ENV_MODE_BEFORE=""
PREVIOUS_EFFECTIVE_ENABLED="false"
ROLLBACK_ARMED=0
MUTATED=0
IDEMPOTENT=0

cleanup_tmp_dir() {
  local dir="${TMP_DIR:-}" parent="" base=""
  [ -z "$dir" ] && return 0
  [ ! -e "$dir" ] && { TMP_DIR=""; return 0; }
  [ -d "$dir" ] || return 1
  parent="$(dirname -- "$dir")"
  base="$(basename -- "$dir")"
  [ "$parent" = "$TMP_PARENT" ] || return 1
  case "$base" in
    ejc-rag-activation.*) ;;
    *) return 1 ;;
  esac
  # Somente arquivos/symlinks diretamente dentro do diretório conhecido.
  # Subdiretórios ou tipos inesperados fazem rmdir falhar e preservam evidência.
  find "$dir" -mindepth 1 -maxdepth 1 \( -type f -o -type l \) -delete
  rmdir -- "$dir"
  TMP_DIR=""
}

json_valid() {
  python3 -c 'import json,sys; json.load(sys.stdin)' >/dev/null 2>&1
}

json_ok() {
  python3 -c 'import json,sys; d=json.load(sys.stdin); raise SystemExit(0 if d.get("ok") is True else 1)' >/dev/null 2>&1
}

json_bool_field() {
  local field="$1"
  python3 -c 'import json,sys; d=json.load(sys.stdin); v=d.get(sys.argv[1]); print("true" if v is True else "false" if v is False else "invalid")' "$field"
}

capture_probe() {
  local output_file="$1" container="$2" mode="$3" override_enabled="$4"
  shift 4
  local output="" rc=0
  set +e
  if [ "$override_enabled" = "1" ]; then
    output="$(docker exec -i -e EMBEDDINGS_ENABLED=true "$container" \
      python - "$mode" "$@" < "$PROBE_SCRIPT")"
    rc=$?
  else
    output="$(docker exec -i "$container" \
      python - "$mode" "$@" < "$PROBE_SCRIPT")"
    rc=$?
  fi
  set -e
  printf '%s\n' "$output" > "$output_file"
  LAST_JSON_FILE="$output_file"
  if ! json_valid < "$output_file"; then
    return 2
  fi
  if [ "$rc" -ne 0 ] || ! json_ok < "$output_file"; then
    return 1
  fi
  return 0
}

env_state() {
  python3 - "$ENV_FILE" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
lines = path.read_text(encoding="utf-8").splitlines()
assignments: list[str] = []
ambiguous: list[str] = []
for line in lines:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        continue
    if re.match(r"^EMBEDDINGS_ENABLED=", line):
        assignments.append(line.split("=", 1)[1].strip().strip("\"'"))
    elif re.match(r"^\s*EMBEDDINGS_ENABLED\s*=", line):
        ambiguous.append(line)
if ambiguous or len(assignments) > 1:
    raise SystemExit(3)
if not assignments:
    print("absent")
    raise SystemExit(0)
value = assignments[0].lower()
if value in {"1", "true", "yes", "on"}:
    print("true")
elif value in {"0", "false", "no", "off"}:
    print("false")
else:
    print("invalid")
PY
}

env_fingerprint_without_flag() {
  python3 - "$ENV_FILE" <<'PY'
from pathlib import Path
import hashlib
import re
import sys

path = Path(sys.argv[1])
kept: list[bytes] = []
for line in path.read_bytes().splitlines(keepends=True):
    text = line.decode("utf-8")
    if re.match(r"^EMBEDDINGS_ENABLED=", text):
        continue
    kept.append(line)
print(hashlib.sha256(b"".join(kept)).hexdigest())
PY
}

set_env_enabled_true() {
  python3 - "$ENV_FILE" <<'PY'
from pathlib import Path
import os
import re
import stat
import sys
import tempfile

path = Path(sys.argv[1])
raw = path.read_text(encoding="utf-8")
lines = raw.splitlines(keepends=True)
matches: list[int] = []
for index, line in enumerate(lines):
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        continue
    if re.match(r"^EMBEDDINGS_ENABLED=", line):
        matches.append(index)
    elif re.match(r"^\s*EMBEDDINGS_ENABLED\s*=", line):
        raise SystemExit("atribuição ambígua de EMBEDDINGS_ENABLED")
if len(matches) > 1:
    raise SystemExit("EMBEDDINGS_ENABLED duplicado")
if matches:
    ending = "\n" if lines[matches[0]].endswith("\n") else ""
    lines[matches[0]] = f"EMBEDDINGS_ENABLED=true{ending}"
else:
    if raw and not raw.endswith("\n"):
        lines.append("\n")
    lines.append("EMBEDDINGS_ENABLED=true\n")
new_text = "".join(lines)
mode = stat.S_IMODE(path.stat().st_mode)
fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.rag.", dir=path.parent)
try:
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
        handle.write(new_text)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(tmp_name, mode)
    os.replace(tmp_name, path)
    dir_fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
finally:
    if os.path.exists(tmp_name):
        os.unlink(tmp_name)
PY
}

atomic_restore_env() {
  python3 - "$ENV_BAK" "$ENV_FILE" <<'PY'
from pathlib import Path
import os
import shutil
import stat
import sys
import tempfile

source = Path(sys.argv[1])
target = Path(sys.argv[2])
mode = stat.S_IMODE(source.stat().st_mode)
fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.restore.", dir=target.parent)
os.close(fd)
try:
    shutil.copyfile(source, tmp_name)
    os.chmod(tmp_name, mode)
    with open(tmp_name, "rb") as handle:
        os.fsync(handle.fileno())
    os.replace(tmp_name, target)
    dir_fd = os.open(target.parent, os.O_DIRECTORY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
finally:
    if os.path.exists(tmp_name):
        os.unlink(tmp_name)
PY
}

wait_backend() {
  for _ in $(seq 1 45); do
    if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

wait_worker() {
  local status=""
  for _ in $(seq 1 60); do
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' \
      "$WORKER_CONTAINER" 2>/dev/null || true)"
    [ "$status" = "healthy" ] && return 0
    sleep 2
  done
  return 1
}

assert_health_commit() {
  local url="$1" expected="$2"
  [ -z "$expected" ] && return 0
  local payload=""
  payload="$(curl -fsS "$url")" || return 1
  printf '%s' "$payload" | python3 -c '
import json,sys
expected=sys.argv[1]
data=json.load(sys.stdin)
raise SystemExit(0 if data.get("commit") == expected else 1)
' "$expected"
}

assert_runtime_enabled() {
  local container="$1" expected="$2" output_file="$3"
  capture_probe "$output_file" "$container" runtime 0 || return 1
  [ "$(json_bool_field EMBEDDINGS_ENABLED < "$output_file")" = "$expected" ]
}

validate_backup_json() {
  python3 -c '
import json,sys
d=json.load(sys.stdin)
required=("ok","local_ok","banco_cifrado","uploads_cifrados")
raise SystemExit(0 if all(d.get(k) is True for k in required) else 1)
' >/dev/null
}

write_success_report() {
  [ -z "$RAG_REPORT_PATH" ] && return 0
  python3 - "$RAG_REPORT_PATH" "$PROOF_JSON_FILE" "$PREFLIGHT_JSON_FILE" \
    "$BACKUP_JSON_FILE" "$CANARY_JSON_FILE" "$PREPROOF_JSON_FILE" \
    "$EXPECTED_GIT_SHA" "$IDEMPOTENT" "$MUTATED" <<'PY'
from pathlib import Path
import json
import os
import sys


def load_optional(path: str):
    p = Path(path)
    if not p.exists() or not p.read_text(encoding="utf-8").strip():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


out = Path(sys.argv[1])
proof = load_optional(sys.argv[2]) or {}
preflight = load_optional(sys.argv[3]) or {}
backup = load_optional(sys.argv[4])
canary = load_optional(sys.argv[5])
preproof = load_optional(sys.argv[6])
proof.update({
    "fase": "ativacao_controlada",
    "ok": True,
    "target_sha": sys.argv[7] or None,
    "idempotente": sys.argv[8] == "1",
    "env_mutado": sys.argv[9] == "1",
    "preflight_ok": preflight.get("ok") is True,
    "backup_cifrado_ok": None if backup is None else all(
        backup.get(k) is True
        for k in ("ok", "local_ok", "banco_cifrado", "uploads_cifrados")
    ),
    "canario_executado": canary is not None,
    "canario_documentos_processados": None if canary is None else canary.get("documentos_processados"),
    "prova_governada_pre_scheduler_ok": None if preproof is None else preproof.get("ok") is True,
    "rollback_executado": False,
    "rollback_ok": None,
})
out.parent.mkdir(parents=True, exist_ok=True)
tmp = out.with_name(f".{out.name}.tmp")
tmp.write_text(json.dumps(proof, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
os.chmod(tmp, 0o600)
os.replace(tmp, out)
PY
}

write_failure_report() {
  local rollback_executed="$1" rollback_ok="$2"
  [ -z "$RAG_REPORT_PATH" ] && return 0
  python3 - "$RAG_REPORT_PATH" "$LAST_JSON_FILE" "$EXPECTED_GIT_SHA" \
    "$rollback_executed" "$rollback_ok" "$MUTATED" <<'PY'
from pathlib import Path
import json
import os
import sys

out = Path(sys.argv[1])
source = Path(sys.argv[2]) if sys.argv[2] else None
base: dict = {}
if source and source.exists():
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
        base = {
            "fase_origem": raw.get("fase"),
            "problemas": [str(item)[:240] for item in raw.get("problemas", [])[:10]],
        }
    except Exception:
        base = {"problemas": ["fase operacional não produziu JSON válido"]}
base.update({
    "fase": "ativacao_controlada_falhou",
    "ok": False,
    "target_sha": sys.argv[3] or None,
    "env_mutado": sys.argv[6] == "1",
    "rollback_executado": sys.argv[4] == "1",
    "rollback_ok": None if sys.argv[4] != "1" else sys.argv[5] == "1",
})
out.parent.mkdir(parents=True, exist_ok=True)
tmp = out.with_name(f".{out.name}.tmp")
tmp.write_text(json.dumps(base, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
os.chmod(tmp, 0o600)
os.replace(tmp, out)
PY
}

on_exit() {
  local rc=$?
  trap - EXIT INT TERM
  local rollback_executed=0 rollback_ok=0
  if [ "$rc" -ne 0 ] && [ "$ROLLBACK_ARMED" = "1" ] && \
     [ -n "$ENV_BAK" ] && [ -f "$ENV_BAK" ]; then
    rollback_executed=1
    set +e
    log "falha detectada; restaurando a configuração anterior."
    atomic_restore_env
    "${DC[@]}" up -d --force-recreate --no-deps backend worker
    if wait_backend && wait_worker && \
       assert_runtime_enabled "$APP_CONTAINER" "$PREVIOUS_EFFECTIVE_ENABLED" "$RUNTIME_BACKEND_JSON" && \
       assert_runtime_enabled "$WORKER_CONTAINER" "$PREVIOUS_EFFECTIVE_ENABLED" "$RUNTIME_WORKER_JSON" && \
       [ "$(sha256sum "$ENV_FILE" | awk '{print $1}')" = "$ENV_SHA_BEFORE" ] && \
       [ "$(stat -c '%a' "$ENV_FILE")" = "$ENV_MODE_BEFORE" ] && \
       assert_health_commit "http://127.0.0.1:8000/api/health" "$EXPECTED_GIT_SHA" && \
       assert_health_commit "$PUBLIC_HEALTH_URL" "$EXPECTED_GIT_SHA"; then
      rollback_ok=1
      rm -f "$ENV_BAK"
      log "rollback confirmado; configuração e runtime anteriores foram restaurados."
    else
      log "ALERTA: rollback não pôde ser comprovado; cópia preservada em $ENV_BAK."
    fi
    set -e
  fi
  if [ "$rc" -ne 0 ]; then
    write_failure_report "$rollback_executed" "$rollback_ok" || true
  fi
  cleanup_tmp_dir || log "ALERTA: diretório temporário preservado para inspeção: ${TMP_DIR:-indisponível}"
  exit "$rc"
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

ENV_STATE="$(env_state)" || die "EMBEDDINGS_ENABLED duplicado ou ambíguo no .env."
[ "$ENV_STATE" != "invalid" ] || die "EMBEDDINGS_ENABLED possui valor inválido no .env."

log "validando configuração efetiva atual no backend e no worker..."
capture_probe "$RUNTIME_BACKEND_JSON" "$APP_CONTAINER" runtime 0 || \
  die "runtime atual do backend é incompatível com o contrato homologado."
capture_probe "$RUNTIME_WORKER_JSON" "$WORKER_CONTAINER" runtime 0 || \
  die "runtime atual do worker é incompatível com o contrato homologado."
BACKEND_ENABLED="$(json_bool_field EMBEDDINGS_ENABLED < "$RUNTIME_BACKEND_JSON")"
WORKER_ENABLED="$(json_bool_field EMBEDDINGS_ENABLED < "$RUNTIME_WORKER_JSON")"
[ "$BACKEND_ENABLED" != "invalid" ] && [ "$BACKEND_ENABLED" = "$WORKER_ENABLED" ] || \
  die "backend e worker divergem quanto a EMBEDDINGS_ENABLED."
PREVIOUS_EFFECTIVE_ENABLED="$BACKEND_ENABLED"
if [ "$ENV_STATE" != "absent" ] && [ "$ENV_STATE" != "$PREVIOUS_EFFECTIVE_ENABLED" ]; then
  die "o .env diverge da configuração efetiva; correção manual é necessária."
fi
if [ "$ENV_STATE" = "absent" ] && [ "$PREVIOUS_EFFECTIVE_ENABLED" = "true" ]; then
  die "runtime ativo sem chave correspondente no .env; origem da configuração é ambígua."
fi

assert_health_commit "http://127.0.0.1:8000/api/health" "$EXPECTED_GIT_SHA" || \
  die "health local não confirma o SHA esperado."
assert_health_commit "$PUBLIC_HEALTH_URL" "$EXPECTED_GIT_SHA" || \
  die "health público não confirma o SHA esperado."

log "executando probe real 1024d antes de qualquer mutação..."
capture_probe "$PREFLIGHT_JSON_FILE" "$APP_CONTAINER" preflight 1 || \
  die "preflight vetorial falhou; nenhuma configuração foi alterada."

if [ "$PREVIOUS_EFFECTIVE_ENABLED" = "true" ]; then
  IDEMPOTENT=1
  log "RAG semântico já está ativo; executando somente prova idempotente."
  capture_probe "$PROOF_JSON_FILE" "$APP_CONTAINER" proof 0 || \
    die "RAG já ativo, porém a prova final falhou."
  assert_runtime_enabled "$WORKER_CONTAINER" true "$RUNTIME_WORKER_JSON" || \
    die "worker não confirma embeddings ativos."
  write_success_report
  cleanup_tmp_dir || die "não foi possível remover o diretório temporário controlado."
  trap - EXIT INT TERM
  log "RAG semântico já estava ativo e foi comprovado sem mutação."
  exit 0
fi

log "exigindo backup local completo e cifrado antes da ativação..."
set +e
BACKUP_OUTPUT="$(bash scripts/backup.sh)"
BACKUP_RC=$?
set -e
printf '%s\n' "$BACKUP_OUTPUT" > "$BACKUP_JSON_FILE"
LAST_JSON_FILE="$BACKUP_JSON_FILE"
[ "$BACKUP_RC" -eq 0 ] && json_valid < "$BACKUP_JSON_FILE" && \
  validate_backup_json < "$BACKUP_JSON_FILE" || \
  die "backup cifrado completo não foi comprovado; nenhuma configuração foi alterada."

ENV_BAK="${ENV_FILE}.bak.rag.$(date +%Y%m%d_%H%M%S)"
cp -p "$ENV_FILE" "$ENV_BAK"
ENV_MODE_BEFORE="$(stat -c '%a' "$ENV_BAK")"
ENV_SHA_BEFORE="$(sha256sum "$ENV_BAK" | awk '{print $1}')"
FINGERPRINT_BEFORE="$(env_fingerprint_without_flag)"
ROLLBACK_ARMED=1

log "alterando atomicamente apenas EMBEDDINGS_ENABLED para true..."
set_env_enabled_true
MUTATED=1
[ "$(stat -c '%a' "$ENV_FILE")" = "$ENV_MODE_BEFORE" ] || die "permissão do .env foi alterada."
[ "$(env_state)" = "true" ] || die "a flag não foi persistida como true."
[ "$(env_fingerprint_without_flag)" = "$FINGERPRINT_BEFORE" ] || \
  die "campo alheio a EMBEDDINGS_ENABLED foi alterado."

# O backend antigo continua com embeddings desativados e, portanto, o scheduler
# não pode drenar o corpus. O canário roda em um subprocesso isolado do worker,
# com override somente naquele processo, antes de recriar o backend.
log "reindexando canário governado de até ${RAG_CANARY_DOCS} documento(s)..."
capture_probe "$CANARY_JSON_FILE" "$WORKER_CONTAINER" canary 1 \
  --max-docs "$RAG_CANARY_DOCS" || die "reindexação canário governada falhou."

log "comprovando busca governada antes de liberar o scheduler..."
capture_probe "$PREPROOF_JSON_FILE" "$WORKER_CONTAINER" proof 1 \
  --skip-continuity || die "prova governada pré-scheduler falhou."

log "recriando backend e worker com a configuração efetiva..."
"${DC[@]}" up -d --force-recreate --no-deps backend worker
wait_backend || die "backend não ficou saudável após a ativação."
wait_worker || die "worker não ficou saudável após a ativação."
assert_runtime_enabled "$APP_CONTAINER" true "$RUNTIME_BACKEND_JSON" || \
  die "backend não carregou EMBEDDINGS_ENABLED=true."
assert_runtime_enabled "$WORKER_CONTAINER" true "$RUNTIME_WORKER_JSON" || \
  die "worker não carregou EMBEDDINGS_ENABLED=true."

log "comprovando corpus, recuperação governada, scheduler e continuidade..."
capture_probe "$PROOF_JSON_FILE" "$APP_CONTAINER" proof 0 || \
  die "prova final do RAG semântico falhou."
assert_health_commit "http://127.0.0.1:8000/api/health" "$EXPECTED_GIT_SHA" || \
  die "health local perdeu a correspondência com o SHA esperado."
assert_health_commit "$PUBLIC_HEALTH_URL" "$EXPECTED_GIT_SHA" || \
  die "health público perdeu a correspondência com o SHA esperado."

write_success_report
ROLLBACK_ARMED=0
rm -f "$ENV_BAK"
cleanup_tmp_dir || die "não foi possível remover o diretório temporário controlado."
trap - EXIT INT TERM
log "RAG semântico ATIVO e comprovado; pendências governadas ficarão a cargo do scheduler."
