#!/usr/bin/env bash
# Watcher local do fallback EJC. Processa PRs abertos para main sem depender do Actions.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
INTERVAL="${EJC_FALLBACK_INTERVAL_SECONDS:-300}"
AUTO_MERGE="${EJC_FALLBACK_AUTO_MERGE:-1}"
ONCE=0
[ "${1:-}" != "--once" ] || ONCE=1

case "$(realpath "$ROOT" 2>/dev/null || printf '%s' "$ROOT")" in
  /opt/ejc|/opt/ejc/*) echo "[fallback-watch] recusado em produção /opt/ejc" >&2; exit 1;;
esac
[ "$(id -u)" -ne 0 ] || { echo "[fallback-watch] não roda como root" >&2; exit 1; }
command -v gh >/dev/null 2>&1 || { echo "[fallback-watch] gh ausente" >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "[fallback-watch] gh não autenticado" >&2; exit 1; }
REPO="${EJC_REPO:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"
STATE_ROOT="${EJC_CI_STATE_ROOT:-${HOME}/.cache/ejc-ci-state}"
mkdir -p "$STATE_ROOT"; chmod 700 "$STATE_ROOT" 2>/dev/null || true

run_cycle() {
  git fetch --quiet origin main || { echo "[fallback-watch] fetch main falhou" >&2; return 0; }
  gh pr list --repo "$REPO" --base main --state open --limit 100 \
    --json number,headRefOid,isDraft,mergeStateStatus,updatedAt \
    --jq '.[] | select(.isDraft == false) | [.number,.headRefOid,.mergeStateStatus] | @tsv' |
  while IFS=$'\t' read -r pr sha merge_state; do
    [ -n "$pr" ] || continue
    marker="$STATE_ROOT/$sha.result"
    if [ -f "$marker" ] && grep -qx 'success' "$marker"; then
      continue
    fi
    if [ -f "$marker" ] && grep -qx 'failure' "$marker" && [ "${EJC_FALLBACK_RETRY_FAILED:-0}" != "1" ]; then
      continue
    fi
    echo "[fallback-watch] validando PR #$pr ($sha, mergeState=$merge_state)"
    set +e
    if [ "$AUTO_MERGE" = "1" ]; then
      "$ROOT/scripts/ci-fallback.sh" --pr "$pr" --merge
    else
      "$ROOT/scripts/ci-fallback.sh" --pr "$pr"
    fi
    rc=$?
    set -e
    if [ "$rc" -eq 0 ]; then printf 'success\n' > "$marker"; else printf 'failure\n' > "$marker"; fi
  done
}

while :; do
  run_cycle
  [ "$ONCE" -eq 0 ] || break
  sleep "$INTERVAL"
done
