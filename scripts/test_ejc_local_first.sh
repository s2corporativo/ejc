#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$ROOT/scripts/ejc-local-first.sh"
[ -f "$SCRIPT" ] || { echo "script local-first ausente" >&2; exit 1; }

TMP="$(mktemp -d)"
cleanup() {
  if [ -d "$TMP" ]; then
    find "$TMP" -depth -mindepth 1 -delete 2>/dev/null || true
    rmdir "$TMP" 2>/dev/null || true
  fi
}
trap cleanup EXIT

mkdir -p "$TMP/repo/scripts"
cp "$SCRIPT" "$TMP/repo/scripts/ejc-local-first.sh"
cat > "$TMP/repo/scripts/ci-local.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf 'dummy-ci mode=%s\n' "${1:-full}"
EOF
chmod +x "$TMP/repo/scripts/ci-local.sh"

cd "$TMP/repo"
git init -q
git config user.email test@example.invalid
git config user.name test
echo base > tracked.txt
git add tracked.txt scripts
git commit -qm init
git switch -qc feat/test-fallback

echo changed >> tracked.txt
echo safe > novo.txt
echo secret > .env.local

ENV_COMMON=(
  EJC_PRODUCTION_DIR=/definitely/not/here
  EJC_RECOVERY_ROOT="$TMP/recovery"
  EJC_GIT_TIMEOUT=1
)

env "${ENV_COMMON[@]}" bash scripts/ejc-local-first.sh register \
  "Fallback técnico" "Validar continuidade local sem GitHub e sem dado real."
TASK="$(cat "$TMP/recovery/repo/last-task")"
test -f "$TASK"
grep -q '^# Fallback técnico$' "$TASK"
grep -q '^\- sincronizacao: pendente$' "$TASK"

if env "${ENV_COMMON[@]}" bash scripts/ejc-local-first.sh register \
  "Segredo proibido" "api_key=valor-nao-deve-ser-registrado" >/dev/null 2>&1; then
  echo "registro com aparência de segredo deveria ter sido bloqueado" >&2
  exit 1
fi

env "${ENV_COMMON[@]}" bash scripts/ejc-local-first.sh checkpoint
CP="$(cat "$TMP/recovery/repo/last-checkpoint")"
test -f "$CP/tracked-working-tree.patch"
test -f "$CP/untracked-safe.tar.gz"
test -f "$CP/repository.bundle"
test -f "$CP/SHA256SUMS"
grep -q '.env.local' "$CP/skipped-untracked.txt"
tar -tzf "$CP/untracked-safe.tar.gz" | grep -q '^novo.txt$'
! tar -tzf "$CP/untracked-safe.tar.gz" | grep -q '.env.local'

env "${ENV_COMMON[@]}" bash scripts/ejc-local-first.sh validate fast | grep -q 'dummy-ci mode=fast'

git remote add origin https://invalid.invalid/ejc.git
env "${ENV_COMMON[@]}" bash scripts/ejc-local-first.sh status >/dev/null 2>&1
grep -q '^offline$' "$TMP/recovery/repo/mode"
env "${ENV_COMMON[@]}" bash scripts/ejc-local-first.sh sync >/dev/null 2>&1
grep -q '^offline$' "$TMP/recovery/repo/mode"
test -f "$TASK"

if env EJC_PRODUCTION_DIR="$TMP/repo" EJC_RECOVERY_ROOT="$TMP/recovery-prod" \
  bash scripts/ejc-local-first.sh checkpoint >/dev/null 2>&1; then
  echo "checkpoint deveria ter sido bloqueado no diretório de produção" >&2
  exit 1
fi

echo "test_ejc_local_first: OK"
