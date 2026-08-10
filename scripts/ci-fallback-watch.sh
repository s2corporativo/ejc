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
REPO="${EJC_REPO:-s2corporativo/ejc}"
STATE_ROOT="${EJC_CI_STATE_ROOT:-${HOME}/.cache/ejc-ci-state}"
mkdir -p "$STATE_ROOT"; chmod 700 "$STATE_ROOT" 2>/dev/null || true

run_cycle() {
  # Falha da API/GitHub não derruba o daemon: o trabalho fica local e uma nova
  # tentativa ocorre no próximo ciclo. Nunca convertemos indisponibilidade em verde.
  if ! gh auth status >/dev/null 2>&1; then
    echo "[fallback-watch] gh indisponível/não autenticado neste ciclo; nova tentativa depois." >&2
    return 0
  fi
  if ! git fetch --quiet origin main; then
    echo "[fallback-watch] GitHub/fetch indisponível neste ciclo; mantendo estado local." >&2
    return 0
  fi

  # O watcher é instalado somente sobre a main limpa. Mantenha o motor local
  # fast-forward para receber correções já integradas, sem reset/force.
  if [ "$(git branch --show-current)" != "main" ] || [ -n "$(git status --porcelain)" ]; then
    echo "[fallback-watch] checkout deixou de ser main limpa; ciclo recusado." >&2
    return 0
  fi
  if ! git merge --ff-only origin/main >/dev/null 2>&1; then
    echo "[fallback-watch] main local não pôde avançar por fast-forward; ciclo recusado." >&2
    return 0
  fi

  local prs_json
  prs_json="$(gh pr list --repo "$REPO" --base main --state open --limit 100 \
    --json number,headRefOid,isDraft,mergeStateStatus,updatedAt 2>/dev/null || true)"
  if [ -z "$prs_json" ]; then
    echo "[fallback-watch] API de PR indisponível neste ciclo." >&2
    return 0
  fi

  printf '%s' "$prs_json" | jq -r '.[] | select(.isDraft == false) | [.number,.headRefOid,.mergeStateStatus] | @tsv' |
  while IFS=$'\t' read -r pr sha merge_state; do
    [ -n "$pr" ] || continue
    marker="$STATE_ROOT/$sha.result"

    # O SHA já passou: não repita a suíte pesada. Se revisão/proteção mudou,
    # reavalie somente a elegibilidade do merge contra o mesmo gate por SHA.
    if [ -f "$marker" ] && grep -qx 'success' "$marker"; then
      if [ "$AUTO_MERGE" = "1" ]; then
        bash "$ROOT/scripts/ci-fallback.sh" --pr "$pr" --merge-only || true
      fi
      continue
    fi
    if [ -f "$marker" ] && grep -qx 'failure' "$marker" && [ "${EJC_FALLBACK_RETRY_FAILED:-0}" != "1" ]; then
      continue
    fi

    echo "[fallback-watch] validando PR #$pr ($sha, mergeState=$merge_state)"
    set +e
    if [ "$AUTO_MERGE" = "1" ]; then
      bash "$ROOT/scripts/ci-fallback.sh" --pr "$pr" --merge
    else
      bash "$ROOT/scripts/ci-fallback.sh" --pr "$pr"
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
