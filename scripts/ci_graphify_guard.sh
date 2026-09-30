#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
TARGET="${CI_COMMIT_TARGET_BRANCH:-main}"

command -v git >/dev/null 2>&1 || {
  echo "GRAPHIFY GATE: git ausente; instale git no step de CI." >&2
  exit 2
}
git fetch --quiet origin "refs/heads/$TARGET:refs/remotes/origin/$TARGET"
BASE="origin/$TARGET"
if [ -n "${CI_COMMIT_BEFORE:-}" ] && git cat-file -e "${CI_COMMIT_BEFORE}^{commit}" 2>/dev/null; then
  BASE="$CI_COMMIT_BEFORE"
fi

mapfile -t DELETED < <(
  git diff --diff-filter=D --name-only "$BASE"...HEAD -- \
    '*.py' '*.js' '*.jsx' '*.ts' '*.tsx' '*.sh' '*.go' '*.rs' '*.java' '*.rb' '*.php' '*.vue' '*.svelte'
)
if [ "${#DELETED[@]}" -eq 0 ]; then
  echo "GRAPHIFY GATE: nenhum arquivo de código removido; skip."
  exit 0
fi

VENV="${GRAPHIFY_CI_VENV:-/tmp/ejc-graphify-ci}"
if [ ! -x "$VENV/bin/graphify" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet "graphifyy==0.9.72"
fi

TMP="$(mktemp -d)"
cleanup() { git worktree remove --force "$TMP/base" >/dev/null 2>&1 || true; rm -rf "$TMP"; }
trap cleanup EXIT
git worktree add --detach "$TMP/base" "origin/$TARGET" >/dev/null
GRAPHIFY_MAX_WORKERS=1 "$VENV/bin/graphify" update "$TMP/base" --force --no-cluster >/tmp/ejc-graphify-gate.log 2>&1 || {
  tail -n 80 /tmp/ejc-graphify-gate.log >&2
  exit 2
}
python3 "$ROOT/scripts/graphify_dependency_gate.py" \
  --graph "$TMP/base/graphify-out/graph.json" --deleted "${DELETED[@]}"
