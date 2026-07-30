#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ACTIVATE="$ROOT/scripts/rag/ativar_embeddings.sh"
PROBE="$ROOT/scripts/rag/provar_ativacao.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

bash -n "$ACTIVATE"
python3 -m py_compile "$PROBE"

updates="$(grep -Ec '^set_env_var [A-Z_]+ ' "$ACTIVATE")"
[ "$updates" -eq 1 ]
grep -q '^set_env_var EMBEDDINGS_ENABLED "true"$' "$ACTIVATE"

COMPOSE="$ROOT/docker-compose.yml"
if [ -f "$COMPOSE" ]; then
  [ "$(grep -Fc 'fastembed_cache:/tmp/fastembed_cache' "$COMPOSE")" -eq 2 ]
  [ "$(grep -Ec '^  fastembed_cache:$' "$COMPOSE")" -eq 1 ]
fi

make_case() {
  local name="$1"
  local app="$TMP/$name"
  mkdir -p "$app/scripts/rag" "$app/scripts" "$app/bin" "$app/state"
  cp "$PROBE" "$app/scripts/rag/provar_ativacao.py"
  printf 'EMBEDDINGS_ENABLED=false\nUNCHANGED=preservar\n' > "$app/.env"
  printf '#!/usr/bin/env bash\nprintf '\''{"ok":true}\\n'\''\n' > "$app/scripts/backup.sh"

  cat > "$app/bin/curl" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
  cat > "$app/bin/docker" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
state="${MOCK_STATE_DIR:?}"

if [ "${1:-}" = "ps" ]; then
  printf 'ejc_backend\nejc_worker\n'
  exit 0
fi
if [ "${1:-}" = "compose" ]; then
  if [ "${2:-}" = "version" ]; then
    exit 0
  fi
  if [ "${2:-}" = "up" ]; then
    printf 'up\n' >> "$state/compose-up"
    exit 0
  fi
fi
if [ "${1:-}" = "inspect" ]; then
  printf 'true\n'
  exit 0
fi
if [ "${1:-}" = "exec" ]; then
  shift
  for arg in "$@"; do
    if [ "$arg" = "preflight" ]; then
      while IFS= read -r _; do :; done || true
      printf '{"fase":"preflight","ok":true,"probe_vetor_dim":1024}\n'
      exit 0
    fi
    if [ "$arg" = "canary" ]; then
      while IFS= read -r _; do :; done || true
      printf '{"fase":"canary","ok":true,"documentos_processados":1}\n'
      exit 0
    fi
    if [ "$arg" = "proof" ]; then
      while IFS= read -r _; do :; done || true
      if [ "${MOCK_FINAL_FAIL:-0}" = "1" ]; then
        printf '{"fase":"proof","ok":false,"problemas":["falha simulada"]}\n'
        exit 1
      fi
      printf '{"fase":"proof","ok":true,"knowledge_chunks_com_embedding":1}\n'
      exit 0
    fi
  done
  exit 0
fi

printf 'docker mock: chamada inesperada\n' >&2
exit 2
EOF
  chmod +x "$app/bin/curl" "$app/bin/docker"
  printf '%s\n' "$app"
}

success_app="$(make_case success)"
PATH="$success_app/bin:$PATH" \
MOCK_STATE_DIR="$success_app/state" \
APP_DIR="$success_app" \
RAG_REPORT_PATH="$success_app/report.json" \
bash "$ACTIVATE" >/dev/null
grep -qx 'EMBEDDINGS_ENABLED=true' "$success_app/.env"
grep -qx 'UNCHANGED=preservar' "$success_app/.env"
grep -q '"ok":true' "$success_app/report.json"
[ "$(wc -l < "$success_app/state/compose-up")" -eq 1 ]
! compgen -G "$success_app/.env.bak.rag.*" >/dev/null

rollback_app="$(make_case rollback)"
set +e
PATH="$rollback_app/bin:$PATH" \
MOCK_STATE_DIR="$rollback_app/state" \
MOCK_FINAL_FAIL=1 \
APP_DIR="$rollback_app" \
RAG_REPORT_PATH="$rollback_app/report.json" \
bash "$ACTIVATE" >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -ne 0 ]
grep -qx 'EMBEDDINGS_ENABLED=false' "$rollback_app/.env"
grep -qx 'UNCHANGED=preservar' "$rollback_app/.env"
grep -q '"ok":false' "$rollback_app/report.json"
[ "$(wc -l < "$rollback_app/state/compose-up")" -eq 2 ]
! compgen -G "$rollback_app/.env.bak.rag.*" >/dev/null

printf 'test_rag_activation: ok\n'
