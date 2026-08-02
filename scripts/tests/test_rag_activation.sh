#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ACTIVATE="$ROOT/scripts/rag/ativar_embeddings.sh"
PROBE="$ROOT/scripts/rag/provar_ativacao.py"
WORKFLOW="$ROOT/.github/workflows/rag-production-activation.yml"
COMPOSE="$ROOT/docker-compose.yml"
REAL_PYTHON="$(command -v python3)"
TMP="$(mktemp -d)"

safe_cleanup() {
  find "$TMP" -depth -mindepth 1 -delete 2>/dev/null || true
  rmdir "$TMP" 2>/dev/null || true
}
trap safe_cleanup EXIT

fail() { printf 'test_rag_activation: ERRO: %s\n' "$*" >&2; exit 1; }
assert_file_contains() { grep -Fq -- "$2" "$1" || fail "$1 não contém: $2"; }
assert_json() {
  local file="$1" expression="$2"
  python3 - "$file" "$expression" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
if not eval(sys.argv[2], {"__builtins__": {}}, {"d": data}):
    raise SystemExit(f"asserção JSON falhou: {sys.argv[2]} — {data}")
PY
}
count_lines() { [ -f "$1" ] && wc -l < "$1" || printf '0\n'; }

bash -n "$ACTIVATE"
python3 -m py_compile "$PROBE"
[ -f "$WORKFLOW" ] || fail "workflow ausente"

# Contratos estáticos de governança, isolamento e segurança.
[ "$(grep -Ec '^set_env_enabled_true$' "$ACTIVATE")" -eq 1 ]
! grep -Eq 'sed[[:space:]]+-i|sudo install|rm[[:space:]]+-rf' "$ACTIVATE"
assert_file_contains "$ACTIVATE" 'cleanup_tmp_dir'
assert_file_contains "$ACTIVATE" 'ejc-rag-activation.XXXXXXXX'
assert_file_contains "$ACTIVATE" 'flock -n 9'
assert_file_contains "$ACTIVATE" 'validate_backup_json'
assert_file_contains "$ACTIVATE" 'env_fingerprint_without_flag'
assert_file_contains "$ACTIVATE" '"$WORKER_CONTAINER" canary 1'
assert_file_contains "$ACTIVATE" '"$WORKER_CONTAINER" proof 1'
assert_file_contains "$ACTIVATE" '--skip-continuity'

canary_line="$(grep -n '"$WORKER_CONTAINER" canary 1' "$ACTIVATE" | cut -d: -f1)"
recreate_line="$(grep -n 'up -d --force-recreate --no-deps backend worker' "$ACTIVATE" | tail -1 | cut -d: -f1)"
[ "$canary_line" -lt "$recreate_line" ] || fail "canário deve ocorrer antes de liberar o scheduler"

assert_file_contains "$WORKFLOW" "'deploy-vps'"
assert_file_contains "$WORKFLOW" "github.ref_name == 'main'"
assert_file_contains "$WORKFLOW" 'ref: ${{ github.sha }}'
assert_file_contains "$WORKFLOW" 'test "$target_sha" = "${{ github.sha }}"'
assert_file_contains "$WORKFLOW" 'cmp -s scripts/rag/ativar_embeddings.sh /opt/ejc/scripts/rag/ativar_embeddings.sh'
! grep -Fq 'sudo install' "$WORKFLOW"

assert_file_contains "$PROBE" 'knowledge_chunks_governados_com_embedding'
assert_file_contains "$PROBE" 'FOR UPDATE OF kd SKIP LOCKED'
assert_file_contains "$PROBE" '_probe_semantic_search'
assert_file_contains "$PROBE" '_filtros_gate_rag(False)'
assert_file_contains "$PROBE" '_FILTRO_ESCOPO_RAG'
assert_file_contains "$PROBE" '_rag_max_dist()'
assert_file_contains "$PROBE" '--skip-continuity'

if [ -f "$COMPOSE" ]; then
  [ "$(grep -Fc 'fastembed_cache:/tmp/fastembed_cache' "$COMPOSE")" -eq 2 ] || \
    fail "cache FastEmbed deve estar montado em backend e worker"
  [ "$(grep -Ec '^  fastembed_cache:$' "$COMPOSE")" -eq 1 ] || \
    fail "volume fastembed_cache deve ser declarado uma vez"
fi

make_case() {
  local name="$1" enabled="${2:-false}"
  local app="$TMP/$name"
  mkdir -p "$app/scripts/rag" "$app/scripts/tests" "$app/scripts" \
    "$app/bin" "$app/state" "$app/tmp"
  cp "$PROBE" "$app/scripts/rag/provar_ativacao.py"
  cp "$ACTIVATE" "$app/scripts/rag/ativar_embeddings.sh"
  printf 'EMBEDDINGS_ENABLED=%s\nUNCHANGED=preservar\n' "$enabled" > "$app/.env"
  printf 'services: {}\n' > "$app/docker-compose.yml"

  cat > "$app/scripts/backup.sh" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
printf 'backup\n' >> "${MOCK_STATE_DIR:?}/backup-called"
if [ "${MOCK_BACKUP_FAIL:-0}" = "1" ]; then
  printf '{"ok":false,"local_ok":false,"banco_cifrado":false,"uploads_cifrados":false}\n'
  exit 1
fi
printf '{"ok":true,"local_ok":true,"banco_cifrado":true,"uploads_cifrados":true,"offsite_ok":false}\n'
MOCK

  cat > "$app/bin/curl" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
[ "${MOCK_HEALTH_FAIL:-0}" != "1" ] || exit 22
printf '{"status":"ok","commit":"%s"}\n' "${MOCK_GIT_SHA:-test-sha}"
MOCK

  cat > "$app/bin/flock" <<'MOCK'
#!/usr/bin/env bash
exit 0
MOCK

  cat > "$app/bin/python3" <<MOCK
#!/usr/bin/env bash
exec "$REAL_PYTHON" -S "\$@"
MOCK

  cat > "$app/bin/docker" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
state="${MOCK_STATE_DIR:?}"
app="${MOCK_APP_DIR:?}"

if [ "${1:-}" = "compose" ]; then
  case "${2:-}" in
    version|config) exit 0 ;;
    up)
      printf 'up\n' >> "$state/compose-up"
      exit 0
      ;;
  esac
fi
if [ "${1:-}" = "inspect" ]; then
  if [ "${MOCK_WORKER_UNHEALTHY:-0}" = "1" ]; then
    printf 'unhealthy\n'
  else
    printf 'healthy\n'
  fi
  exit 0
fi
if [ "${1:-}" != "exec" ]; then
  printf 'docker mock: chamada inesperada: %s\n' "$*" >&2
  exit 2
fi

for arg in "$@"; do
  [ "$arg" = "true" ] && exit 0
done

container=""
mode=""
override=false
skip_continuity=false
for arg in "$@"; do
  case "$arg" in
    ejc_backend|ejc_worker) container="$arg" ;;
    runtime|preflight|canary|proof) mode="$arg" ;;
    EMBEDDINGS_ENABLED=true) override=true ;;
    --skip-continuity) skip_continuity=true ;;
  esac
done
[ -n "$container" ] && [ -n "$mode" ] || exit 2

read_enabled() {
  local value
  value="$(grep '^EMBEDDINGS_ENABLED=' "$app/.env" | tail -1 | cut -d= -f2-)"
  case "${value,,}" in true|1|yes|on) printf true ;; *) printf false ;; esac
}

enabled="$(read_enabled)"
[ "$override" = false ] || enabled=true
if [ "$mode" = "runtime" ] && [ "$container" = "ejc_worker" ] && \
   [ "${MOCK_WORKER_STALE_AFTER_UP:-0}" = "1" ] && [ -s "$state/compose-up" ]; then
  enabled=false
fi

common='"EMBEDDINGS_PROVIDER":"local","EMBEDDINGS_MODEL":"intfloat/multilingual-e5-large","embedding_dim_configurada":1024,"modelo_valido":true,"ENABLE_SCHEDULER":true,"RAG_AUTO_REEMBED_ENABLED":true'
case "$mode" in
  runtime)
    printf '{"fase":"runtime","ok":true,"EMBEDDINGS_ENABLED":%s,%s,"problemas":[]}\n' "$enabled" "$common"
    ;;
  preflight)
    if [ "${MOCK_PREFLIGHT_FAIL:-0}" = "1" ]; then
      printf '{"fase":"preflight","ok":false,"problemas":["falha simulada"]}\n'
      exit 1
    fi
    printf '{"fase":"preflight","ok":true,"EMBEDDINGS_ENABLED":true,%s,"embedding_dim_coluna":1024,"probe_vetor_ok":true,"probe_pgvector_ok":true,"problemas":[]}\n' "$common"
    ;;
  canary)
    printf 'canary\n' >> "$state/canary-called"
    printf '%s:%s\n' "$container" "$override" >> "$state/canary-context"
    if [ "${MOCK_CANARY_FAIL:-0}" = "1" ]; then
      printf '{"fase":"canary","ok":false,"problemas":["falha simulada"]}\n'
      exit 1
    fi
    printf '{"fase":"canary","ok":true,"documentos_processados":1,"documentos_ok":1,"documentos_com_erro":0,"knowledge_chunks_governados_com_embedding":1,"knowledge_chunks_governados_pendentes":0,"problemas":[]}\n'
    ;;
  proof)
    count=0
    [ ! -f "$state/proof-count" ] || count="$(cat "$state/proof-count")"
    count=$((count + 1))
    printf '%s\n' "$count" > "$state/proof-count"
    printf '%s:%s:%s\n' "$container" "$override" "$skip_continuity" >> "$state/proof-context"
    if [ "${MOCK_PREPROOF_FAIL:-0}" = "1" ] && [ "$skip_continuity" = true ]; then
      printf '{"fase":"proof","ok":false,"problemas":["pré-prova simulada"]}\n'
      exit 1
    fi
    if [ "${MOCK_FINAL_PROOF_FAIL:-0}" = "1" ] && [ "$skip_continuity" = false ]; then
      printf '{"fase":"proof","ok":false,"problemas":["prova final simulada"]}\n'
      exit 1
    fi
    printf '{"fase":"proof","ok":true,"EMBEDDINGS_ENABLED":%s,%s,"knowledge_chunks_vigentes_total":1,"knowledge_chunks_vigentes_com_embedding":1,"knowledge_chunks_vigentes_pendentes":0,"knowledge_chunks_governados_total":1,"knowledge_chunks_governados_com_embedding":1,"probe_busca_semantica_governada_ok":true,"probe_busca_semantica_ok":true,"continuidade_exigida":%s,"problemas":[]}\n' "$enabled" "$common" "$([ "$skip_continuity" = true ] && printf false || printf true)"
    ;;
esac
MOCK
  chmod +x "$app/scripts/backup.sh" "$app/bin/curl" "$app/bin/docker" \
    "$app/bin/flock" "$app/bin/python3"
  printf '%s\n' "$app"
}

run_case() {
  local app="$1"
  shift
  env PATH="$app/bin:$PATH" \
    TMPDIR="$app/tmp" \
    MOCK_STATE_DIR="$app/state" \
    MOCK_APP_DIR="$app" \
    MOCK_GIT_SHA=test-sha \
    APP_DIR="$app" \
    RAG_LOCK_FILE="$app/state/rag.lock" \
    RAG_REPORT_PATH="$app/report.json" \
    EXPECTED_GIT_SHA=test-sha \
    PUBLIC_HEALTH_URL=https://example.invalid/api/health \
    "$@" bash "$ACTIVATE"
}

# 1. Ativação normal: canário + prova governada no worker antes do único recreate.
success_app="$(make_case success false)"
run_case "$success_app" >/dev/null
grep -qx 'EMBEDDINGS_ENABLED=true' "$success_app/.env"
grep -qx 'UNCHANGED=preservar' "$success_app/.env"
[ "$(count_lines "$success_app/state/compose-up")" -eq 1 ]
[ "$(count_lines "$success_app/state/backup-called")" -eq 1 ]
[ "$(count_lines "$success_app/state/canary-called")" -eq 1 ]
grep -qx 'ejc_worker:true' "$success_app/state/canary-context"
sed -n '1p' "$success_app/state/proof-context" | grep -qx 'ejc_worker:true:true'
sed -n '2p' "$success_app/state/proof-context" | grep -qx 'ejc_backend:false:false'
! compgen -G "$success_app/.env.bak.rag.*" >/dev/null
assert_json "$success_app/report.json" 'd["ok"] is True and d["env_mutado"] is True and d["prova_governada_pre_scheduler_ok"] is True and d["rollback_executado"] is False'

# 2. Falha da pré-prova: scheduler nunca é liberado; rollback recria estado anterior uma vez.
preproof_app="$(make_case preproof false)"
set +e
run_case "$preproof_app" MOCK_PREPROOF_FAIL=1 >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -ne 0 ]
grep -qx 'EMBEDDINGS_ENABLED=false' "$preproof_app/.env"
[ "$(count_lines "$preproof_app/state/compose-up")" -eq 1 ]
assert_json "$preproof_app/report.json" 'd["ok"] is False and d["rollback_executado"] is True and d["rollback_ok"] is True'

# 3. Falha final após recreate: rollback byte a byte e segundo recreate.
final_app="$(make_case final false)"
set +e
run_case "$final_app" MOCK_FINAL_PROOF_FAIL=1 >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -ne 0 ]
grep -qx 'EMBEDDINGS_ENABLED=false' "$final_app/.env"
grep -qx 'UNCHANGED=preservar' "$final_app/.env"
[ "$(count_lines "$final_app/state/compose-up")" -eq 2 ]
assert_json "$final_app/report.json" 'd["ok"] is False and d["rollback_executado"] is True and d["rollback_ok"] is True'

# 4. Canário falha fechado e dispara rollback sem liberar o backend com scheduler.
canary_app="$(make_case canary false)"
set +e
run_case "$canary_app" MOCK_CANARY_FAIL=1 >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -ne 0 ]
grep -qx 'EMBEDDINGS_ENABLED=false' "$canary_app/.env"
[ "$(count_lines "$canary_app/state/compose-up")" -eq 1 ]

# 5. Preflight falha antes de backup/mutação.
preflight_app="$(make_case preflight false)"
set +e
run_case "$preflight_app" MOCK_PREFLIGHT_FAIL=1 >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -ne 0 ]
grep -qx 'EMBEDDINGS_ENABLED=false' "$preflight_app/.env"
[ ! -e "$preflight_app/state/backup-called" ]
[ ! -e "$preflight_app/state/compose-up" ]
assert_json "$preflight_app/report.json" 'd["ok"] is False and d["env_mutado"] is False and d["rollback_executado"] is False'

# 6. Backup incompleto bloqueia antes de mutar.
backup_app="$(make_case backup false)"
set +e
run_case "$backup_app" MOCK_BACKUP_FAIL=1 >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -ne 0 ]
grep -qx 'EMBEDDINGS_ENABLED=false' "$backup_app/.env"
[ ! -e "$backup_app/state/compose-up" ]
assert_json "$backup_app/report.json" 'd["ok"] is False and d["env_mutado"] is False'

# 7. Configuração duplicada falha fechada, sem backup nem mutação.
duplicate_app="$(make_case duplicate false)"
printf 'EMBEDDINGS_ENABLED=true\n' >> "$duplicate_app/.env"
set +e
run_case "$duplicate_app" >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -ne 0 ]
[ ! -e "$duplicate_app/state/backup-called" ]
[ ! -e "$duplicate_app/state/compose-up" ]

# 8. Já ativo: prova idempotente, sem backup, recreate ou canário.
idempotent_app="$(make_case idempotent true)"
run_case "$idempotent_app" >/dev/null
[ ! -e "$idempotent_app/state/backup-called" ]
[ ! -e "$idempotent_app/state/compose-up" ]
[ ! -e "$idempotent_app/state/canary-called" ]
assert_json "$idempotent_app/report.json" 'd["ok"] is True and d["idempotente"] is True and d["env_mutado"] is False'

# 9. Worker que não carrega a flag após recreate força rollback comprovado.
stale_app="$(make_case stale false)"
set +e
run_case "$stale_app" MOCK_WORKER_STALE_AFTER_UP=1 >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -ne 0 ]
grep -qx 'EMBEDDINGS_ENABLED=false' "$stale_app/.env"
[ "$(count_lines "$stale_app/state/compose-up")" -eq 2 ]
assert_json "$stale_app/report.json" 'd["rollback_executado"] is True and d["rollback_ok"] is True'

printf 'test_rag_activation: ok\n'
