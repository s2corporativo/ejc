#!/usr/bin/env bash
# Watcher persistente do fallback EJC.
# Processa PRs abertos contra main, reutiliza apenas evidência íntegra do SHA e
# aplica retry limitado exclusivamente a indisponibilidade de infraestrutura.
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
INTERVAL="${EJC_FALLBACK_INTERVAL_SECONDS:-300}"
AUTO_MERGE="${EJC_FALLBACK_AUTO_MERGE:-1}"
INFRA_MAX_RETRIES="${EJC_FALLBACK_INFRA_MAX_RETRIES:-3}"
INFRA_RETRY_BASE_SECONDS="${EJC_FALLBACK_INFRA_RETRY_SECONDS:-300}"
INFRA_RETRY_MAX_SECONDS="${EJC_FALLBACK_INFRA_RETRY_MAX_SECONDS:-1800}"
GREEN_RECHECK_SECONDS="${EJC_FALLBACK_GREEN_RECHECK_SECONDS:-1800}"
PR_LIMIT="${EJC_FALLBACK_PR_LIMIT:-500}"
ONCE=0
[ "${1:-}" != "--once" ] || ONCE=1

canon() {
  if command -v realpath >/dev/null 2>&1; then realpath -m "$1"; else printf '%s\n' "$1"; fi
}

fail() { printf '[fallback-watch] ERRO: %s\n' "$*" >&2; exit 1; }

ROOT_CANON="$(canon "$ROOT")"
case "$ROOT_CANON" in
  /opt/ejc|/opt/ejc/*) fail "recusado em produção /opt/ejc" ;;
esac
[ "$(id -u)" -ne 0 ] || fail "não roda como root"
[ "${APP_ENV:-}" != "production" ] && [ "${EJC_ENV:-}" != "production" ] || fail "ambiente de produção ativo"
[ ! -e /opt/ejc/.deployed_sha ] && [ ! -e /opt/ejc/.env ] || fail "host contém marcadores da produção"
for cmd in gh jq python3 git; do command -v "$cmd" >/dev/null 2>&1 || fail "$cmd ausente"; done
[ -f "$ROOT/scripts/ci_evidence.py" ] || fail "ci_evidence.py ausente"

REPO="${EJC_REPO:-s2corporativo/ejc}"
[[ "$REPO" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || fail "EJC_REPO inválido"
CACHE_ROOT="${EJC_CI_STATE_ROOT:-${XDG_CACHE_HOME:-${HOME:-/tmp}/.cache}/ejc-ci-fallback}"
STATE_ROOT="$CACHE_ROOT/state"
EVIDENCE_ROOT="${EJC_CI_EVIDENCE_ROOT:-$CACHE_ROOT/evidence}"
DRAIN_FILE="${EJC_FALLBACK_DRAIN_FILE:-$CACHE_ROOT/draining}"

assert_safe_state_path() {
  local path="$1" label="$2" resolved home_resolved
  resolved="$(canon "$path")"
  home_resolved="$(canon "${HOME:-/__no_home__}")"
  case "$resolved" in
    /|"$home_resolved"|/opt/ejc|/opt/ejc/*|"$ROOT_CANON"|"$ROOT_CANON"/*)
      fail "$label deve ficar fora do checkout, HOME raiz e produção: $resolved"
      ;;
  esac
}

assert_safe_state_path "$CACHE_ROOT" "CACHE_ROOT"
assert_safe_state_path "$STATE_ROOT" "STATE_ROOT"
assert_safe_state_path "$EVIDENCE_ROOT" "EVIDENCE_ROOT"
assert_safe_state_path "$(dirname "$DRAIN_FILE")" "DRAIN_FILE parent"
mkdir -p "$STATE_ROOT" "$EVIDENCE_ROOT"
chmod 700 "$CACHE_ROOT" "$STATE_ROOT" "$EVIDENCE_ROOT" 2>/dev/null || true

for numeric_name in INTERVAL INFRA_MAX_RETRIES INFRA_RETRY_BASE_SECONDS INFRA_RETRY_MAX_SECONDS GREEN_RECHECK_SECONDS PR_LIMIT; do
  value="${!numeric_name}"
  [[ "$value" =~ ^[0-9]+$ ]] || fail "$numeric_name deve ser inteiro não negativo"
done
[ "$INTERVAL" -gt 0 ] || fail "INTERVAL deve ser > 0"
[ "$INFRA_RETRY_BASE_SECONDS" -gt 0 ] || fail "INFRA_RETRY_BASE_SECONDS deve ser > 0"
[ "$INFRA_RETRY_MAX_SECONDS" -gt 0 ] || fail "INFRA_RETRY_MAX_SECONDS deve ser > 0"
[ "$GREEN_RECHECK_SECONDS" -gt 0 ] || fail "GREEN_RECHECK_SECONDS deve ser > 0"
[ "$PR_LIMIT" -gt 0 ] || fail "PR_LIMIT deve ser > 0"

# Apenas sinais de transporte/registry entram em retry. HTTP funcional do EJC
# não é classificado por um código isolado, evitando mascarar teste real.
INFRA_ERROR_RE='Could not resolve host|Temporary failure in name resolution|Name or service not known|EAI_AGAIN|ECONNRESET|ETIMEDOUT|ENETUNREACH|TLS handshake timeout|Connection timed out|Read timed out|Could not fetch URL|credencial efêmera do GitHub App não pôde ser emitida|não foi possível obter installation token|npm ERR!.*(EAI_AGAIN|ECONNRESET|ETIMEDOUT|429 Too Many Requests|502 Bad Gateway|503 Service Unavailable|504 Gateway Timeout)|registry\.npmjs\.org.*(EAI_AGAIN|ECONNRESET|ETIMEDOUT|429|502|503|504)|pypi\.org.*(Temporary failure|timed out|429|502|503|504)|files\.pythonhosted\.org.*(Temporary failure|timed out|429|502|503|504)|github\.com.*(Could not resolve|timed out|429|502|503|504)'

atomic_text() {
  local file="$1" value="$2" tmp="$file.tmp.$$"
  printf '%s\n' "$value" > "$tmp"
  chmod 600 "$tmp" 2>/dev/null || true
  mv "$tmp" "$file"
}

local_evidence_green() {
  local sha="$1"
  python3 "$ROOT/scripts/ci_evidence.py" verify --sha-root "$EVIDENCE_ROOT/$sha" --sha "$sha" >/dev/null 2>&1
}

latest_attempt_log() {
  local sha="$1" started="$2"
  python3 "$ROOT/scripts/ci_evidence.py" latest-log --sha-root "$EVIDENCE_ROOT/$sha" --sha "$sha" --started-epoch "$started" 2>/dev/null
}

failure_is_infrastructure() {
  local sha="$1" started="$2" invocation_log="$3" stage_log
  stage_log="$(latest_attempt_log "$sha" "$started" 2>/dev/null || true)"
  if [ -n "$stage_log" ] && grep -Eiq "$INFRA_ERROR_RE" -- "$stage_log"; then
    return 0
  fi
  [ -f "$invocation_log" ] && grep -Eiq "$INFRA_ERROR_RE" -- "$invocation_log"
}

retry_delay_seconds() {
  local attempts="$1" delay="$INFRA_RETRY_BASE_SECONDS" i=1
  while [ "$i" -lt "$attempts" ]; do
    delay=$((delay * 2))
    if [ "$delay" -ge "$INFRA_RETRY_MAX_SECONDS" ]; then
      delay="$INFRA_RETRY_MAX_SECONDS"
      break
    fi
    i=$((i + 1))
  done
  printf '%s\n' "$delay"
}

read_retry_state() {
  local file="$1"
  RETRY_ATTEMPTS=0
  RETRY_LAST_EPOCH=0
  [ -s "$file" ] || return 0
  RETRY_ATTEMPTS="$(jq -r '.attempts // 0' "$file" 2>/dev/null || echo 0)"
  RETRY_LAST_EPOCH="$(jq -r '.last_epoch // 0' "$file" 2>/dev/null || echo 0)"
  [[ "$RETRY_ATTEMPTS" =~ ^[0-9]+$ ]] || RETRY_ATTEMPTS=0
  [[ "$RETRY_LAST_EPOCH" =~ ^[0-9]+$ ]] || RETRY_LAST_EPOCH=0
}

write_retry_state() {
  local file="$1" sha="$2" attempts="$3" now="$4" tmp="$file.tmp.$$"
  jq -n --arg sha "$sha" --argjson attempts "$attempts" --argjson last_epoch "$now" '{sha:$sha,classification:"infrastructure",attempts:$attempts,last_epoch:$last_epoch}' > "$tmp"
  chmod 600 "$tmp" 2>/dev/null || true
  mv "$tmp" "$file"
}

pr_state_due() {
  local file="$1" fingerprint="$2" now="$3" old_fingerprint last_epoch
  [ -s "$file" ] || return 0
  old_fingerprint="$(jq -r '.fingerprint // ""' "$file" 2>/dev/null || true)"
  last_epoch="$(jq -r '.last_processed_epoch // 0' "$file" 2>/dev/null || echo 0)"
  [[ "$last_epoch" =~ ^[0-9]+$ ]] || last_epoch=0
  [ "$old_fingerprint" != "$fingerprint" ] && return 0
  [ $((now - last_epoch)) -ge "$GREEN_RECHECK_SECONDS" ]
}

write_pr_state() {
  local file="$1" pr="$2" sha="$3" updated="$4" merge_state="$5" now="$6" result="$7" tmp="$file.tmp.$$"
  local fingerprint="$sha|$updated|$merge_state|$AUTO_MERGE"
  jq -n --argjson pr "$pr" --arg sha "$sha" --arg updated "$updated" --arg merge_state "$merge_state" --arg fingerprint "$fingerprint" --arg result "$result" --argjson last_processed_epoch "$now" '{schema:1,pr:$pr,sha:$sha,updated_at:$updated,merge_state:$merge_state,fingerprint:$fingerprint,result:$result,last_processed_epoch:$last_processed_epoch}' > "$tmp"
  chmod 600 "$tmp" 2>/dev/null || true
  mv "$tmp" "$file"
}

run_cycle() {
  if [ -e "$DRAIN_FILE" ]; then
    echo "[fallback-watch] drain ativo; ciclo pulado sem acessar PRs." >&2
    return 0
  fi
  if ! gh auth status >/dev/null 2>&1; then
    echo "[fallback-watch] gh indisponível/não autenticado neste ciclo; nova tentativa depois." >&2
    return 0
  fi
  if ! git fetch --quiet origin main; then
    echo "[fallback-watch] GitHub/fetch indisponível neste ciclo; mantendo estado local." >&2
    return 0
  fi
  if [ "$(git branch --show-current)" != "main" ] || [ -n "$(git status --porcelain)" ]; then
    echo "[fallback-watch] checkout deixou de ser main limpa; ciclo recusado." >&2
    return 0
  fi
  if ! git merge --ff-only origin/main >/dev/null 2>&1; then
    echo "[fallback-watch] main local não pôde avançar por fast-forward; ciclo recusado." >&2
    return 0
  fi

  local prs_json
  prs_json="$(gh pr list --repo "$REPO" --base main --state open --limit "$PR_LIMIT" --json number,headRefOid,isDraft,mergeStateStatus,updatedAt 2>/dev/null || true)"
  if [ -z "$prs_json" ]; then
    echo "[fallback-watch] API de PR indisponível neste ciclo." >&2
    return 0
  fi

  printf '%s' "$prs_json" | jq -r '.[] | select(.isDraft == false) | [.number,.headRefOid,.mergeStateStatus,.updatedAt] | @tsv' |
  while IFS=$'\t' read -r pr sha merge_state updated_at; do
    [ -n "$pr" ] || continue
    [[ "$pr" =~ ^[1-9][0-9]*$ ]] || continue
    [[ "$sha" =~ ^[0-9a-f]{40}$ ]] || continue

    local marker retry_file pr_state invocation_log now fingerprint delay attempts started rc
    marker="$STATE_ROOT/$sha.result"
    retry_file="$STATE_ROOT/$sha.infra-retry.json"
    pr_state="$STATE_ROOT/pr-$pr.json"
    invocation_log="$STATE_ROOT/$sha.invocation.log"
    now="$(date +%s)"
    fingerprint="$sha|$updated_at|$merge_state|$AUTO_MERGE"

    if local_evidence_green "$sha"; then
      atomic_text "$marker" success
      rm -f "$retry_file"
      if ! pr_state_due "$pr_state" "$fingerprint" "$now"; then
        continue
      fi
      : > "$invocation_log"
      chmod 600 "$invocation_log" 2>/dev/null || true
      set +e
      if [ "$AUTO_MERGE" = "1" ]; then
        bash "$ROOT/scripts/ci-fallback.sh" --pr "$pr" --merge-only >>"$invocation_log" 2>&1
      else
        bash "$ROOT/scripts/ci-fallback.sh" --pr "$pr" --promote-only >>"$invocation_log" 2>&1
      fi
      rc=$?
      set -e
      [ "$rc" -eq 75 ] && continue
      write_pr_state "$pr_state" "$pr" "$sha" "$updated_at" "$merge_state" "$now" "green-sync-rc-$rc"
      continue
    fi

    if [ -f "$marker" ] && grep -qx 'failure' "$marker"; then
      if [ ! -s "$retry_file" ]; then
        [ "${EJC_FALLBACK_RETRY_FAILED:-0}" = "1" ] || continue
      else
        read_retry_state "$retry_file"
        if [ "$RETRY_ATTEMPTS" -ge "$INFRA_MAX_RETRIES" ]; then
          echo "[fallback-watch] PR #$pr atingiu $RETRY_ATTEMPTS retries de infraestrutura; retido até novo SHA." >&2
          continue
        fi
        delay="$(retry_delay_seconds "$RETRY_ATTEMPTS")"
        if [ $((now - RETRY_LAST_EPOCH)) -lt "$delay" ]; then
          continue
        fi
      fi
    fi

    : > "$invocation_log"
    chmod 600 "$invocation_log" 2>/dev/null || true
    echo "[fallback-watch] validando PR #$pr ($sha, mergeState=$merge_state)"
    started="$now"
    set +e
    if [ "$AUTO_MERGE" = "1" ]; then
      bash "$ROOT/scripts/ci-fallback.sh" --pr "$pr" --merge >>"$invocation_log" 2>&1
    else
      bash "$ROOT/scripts/ci-fallback.sh" --pr "$pr" >>"$invocation_log" 2>&1
    fi
    rc=$?
    set -e

    if [ "$rc" -eq 75 ]; then
      atomic_text "$marker" pending
      continue
    fi
    if local_evidence_green "$sha"; then
      atomic_text "$marker" success
      rm -f "$retry_file"
      write_pr_state "$pr_state" "$pr" "$sha" "$updated_at" "$merge_state" "$(date +%s)" "suite-success"
      continue
    fi
    if [ "$rc" -eq 0 ]; then
      atomic_text "$marker" pending
      continue
    fi

    if failure_is_infrastructure "$sha" "$started" "$invocation_log"; then
      read_retry_state "$retry_file"
      attempts=$((RETRY_ATTEMPTS + 1))
      now="$(date +%s)"
      write_retry_state "$retry_file" "$sha" "$attempts" "$now"
      atomic_text "$marker" failure
      if [ "$attempts" -lt "$INFRA_MAX_RETRIES" ]; then
        delay="$(retry_delay_seconds "$attempts")"
        echo "[fallback-watch] PR #$pr falhou por infraestrutura; retry $attempts/$INFRA_MAX_RETRIES após ${delay}s." >&2
      else
        echo "[fallback-watch] PR #$pr atingiu o limite de $INFRA_MAX_RETRIES falhas transitórias; nenhum falso verde." >&2
      fi
    else
      rm -f "$retry_file"
      atomic_text "$marker" failure
      echo "[fallback-watch] PR #$pr reprovou em teste/gate real; mesmo SHA não será repetido automaticamente." >&2
    fi
  done
}

while :; do
  run_cycle
  [ "$ONCE" -eq 0 ] || break
  sleep "$INTERVAL"
done
