#!/usr/bin/env bash
# Watcher local do fallback EJC. Processa PRs abertos para main sem depender do Actions.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
INTERVAL="${EJC_FALLBACK_INTERVAL_SECONDS:-300}"
AUTO_MERGE="${EJC_FALLBACK_AUTO_MERGE:-1}"
INFRA_MAX_RETRIES="${EJC_FALLBACK_INFRA_MAX_RETRIES:-3}"
INFRA_RETRY_BASE_SECONDS="${EJC_FALLBACK_INFRA_RETRY_SECONDS:-300}"
INFRA_RETRY_MAX_SECONDS="${EJC_FALLBACK_INFRA_RETRY_MAX_SECONDS:-1800}"
ONCE=0
[ "${1:-}" != "--once" ] || ONCE=1

case "$(realpath "$ROOT" 2>/dev/null || printf '%s' "$ROOT")" in
  /opt/ejc|/opt/ejc/*) echo "[fallback-watch] recusado em produção /opt/ejc" >&2; exit 1;;
esac
[ "$(id -u)" -ne 0 ] || { echo "[fallback-watch] não roda como root" >&2; exit 1; }
command -v gh >/dev/null 2>&1 || { echo "[fallback-watch] gh ausente" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "[fallback-watch] jq ausente" >&2; exit 1; }
REPO="${EJC_REPO:-s2corporativo/ejc}"
STATE_ROOT="${EJC_CI_STATE_ROOT:-${HOME}/.cache/ejc-ci-state}"
EVIDENCE_ROOT="${EJC_CI_EVIDENCE_ROOT:-${HOME}/.cache/ejc-ci-evidence}"
mkdir -p "$STATE_ROOT" "$EVIDENCE_ROOT"
chmod 700 "$STATE_ROOT" "$EVIDENCE_ROOT" 2>/dev/null || true

# Só sinais inequívocos de infraestrutura externa entram em retry automático.
# Falha de pytest/typecheck/lint/build sem estes sinais é falha real do SHA e
# permanece retida até novo commit.
INFRA_ERROR_RE='Could not resolve host|Temporary failure in name resolution|Name or service not known|EAI_AGAIN|ECONNRESET|ETIMEDOUT|ENETUNREACH|TLS handshake timeout|Connection timed out|Read timed out|429 Too Many Requests|502 Bad Gateway|503 Service Unavailable|504 Gateway Timeout|Could not fetch URL|npm ERR! code (EAI_AGAIN|ECONNRESET|ETIMEDOUT)|registry\.npmjs\.org.*(EAI_AGAIN|ECONNRESET|ETIMEDOUT)|pypi\.org.*(Temporary failure|timed out|502|503|504)|github\.com.*(Could not resolve|timed out|502|503|504)'

local_evidence_green() {
  local sha="$1" summary="$EVIDENCE_ROOT/$1/summary.json"
  [ -s "$summary" ] || return 1
  jq -e --arg sha "$sha" '.target_sha == $sha and .result == "success"' "$summary" >/dev/null 2>&1
}

latest_attempt_log() {
  local sha="$1" started="$2" dir="$EVIDENCE_ROOT/$1"
  [ -d "$dir" ] || return 1
  local file ts best="" best_ts=0
  for file in "$dir"/*.log; do
    [ -f "$file" ] || continue
    ts="$(stat -c %Y "$file" 2>/dev/null || echo 0)"
    [ "$ts" -ge "$started" ] || continue
    if [ "$ts" -ge "$best_ts" ]; then
      best="$file"
      best_ts="$ts"
    fi
  done
  [ -n "$best" ] || return 1
  printf '%s\n' "$best"
}

failure_is_infrastructure() {
  local sha="$1" started="$2" logfile
  logfile="$(latest_attempt_log "$sha" "$started" 2>/dev/null || true)"
  [ -n "$logfile" ] || return 1
  grep -Eiq "$INFRA_ERROR_RE" "$logfile"
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
}

write_retry_state() {
  local file="$1" sha="$2" attempts="$3" now="$4"
  umask 077
  jq -n --arg sha "$sha" --argjson attempts "$attempts" --argjson last_epoch "$now" \
    '{sha:$sha,classification:"infrastructure",attempts:$attempts,last_epoch:$last_epoch}' > "$file"
}

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
    retry_file="$STATE_ROOT/$sha.infra-retry.json"

    # Evidência local integral é a fonte para decidir se a suíte pesada precisa
    # repetir. Metadados/reviews/API podem mudar sem mudar o SHA e são reavaliados
    # sem repetir backend/frontend.
    if local_evidence_green "$sha"; then
      printf 'success\n' > "$marker"
      rm -f "$retry_file"
      if [ "$AUTO_MERGE" = "1" ]; then
        bash "$ROOT/scripts/ci-fallback.sh" --pr "$pr" --merge-only || true
      else
        # Revalida governança e ressincroniza status, mas NÃO tenta merge.
        bash "$ROOT/scripts/ci-fallback.sh" --pr "$pr" --promote-only || true
      fi
      continue
    fi

    # Falha real de código/teste sem evidência integral continua retida. Uma
    # falha classificada como infraestrutura pode repetir no mesmo SHA somente
    # até o teto configurado e respeitando backoff exponencial.
    if [ -f "$marker" ] && grep -qx 'failure' "$marker"; then
      if [ ! -s "$retry_file" ]; then
        [ "${EJC_FALLBACK_RETRY_FAILED:-0}" = "1" ] || continue
      else
        read_retry_state "$retry_file"
        if [ "$RETRY_ATTEMPTS" -ge "$INFRA_MAX_RETRIES" ]; then
          echo "[fallback-watch] PR #$pr atingiu $RETRY_ATTEMPTS retries de infraestrutura; retido até novo SHA." >&2
          continue
        fi
        now="$(date +%s)"
        delay="$(retry_delay_seconds "$RETRY_ATTEMPTS")"
        if [ $((now - RETRY_LAST_EPOCH)) -lt "$delay" ]; then
          continue
        fi
      fi
    fi

    echo "[fallback-watch] validando PR #$pr ($sha, mergeState=$merge_state)"
    started="$(date +%s)"
    set +e
    if [ "$AUTO_MERGE" = "1" ]; then
      bash "$ROOT/scripts/ci-fallback.sh" --pr "$pr" --merge
    else
      bash "$ROOT/scripts/ci-fallback.sh" --pr "$pr"
    fi
    rc=$?
    set -e

    # Se a suíte completa gerou summary success, uma falha posterior de
    # governança mutável/status/API NÃO transforma o código em reprovado. O
    # próximo ciclo fará merge-only/promote-only e revalidará metadados.
    if local_evidence_green "$sha"; then
      printf 'success\n' > "$marker"
      rm -f "$retry_file"
      continue
    fi

    if [ "$rc" -eq 0 ]; then
      # Exit 0 sem summary integral nunca é suficiente para promover o SHA.
      printf 'pending\n' > "$marker"
      continue
    fi

    if failure_is_infrastructure "$sha" "$started"; then
      read_retry_state "$retry_file"
      attempts=$((RETRY_ATTEMPTS + 1))
      now="$(date +%s)"
      write_retry_state "$retry_file" "$sha" "$attempts" "$now"
      printf 'failure\n' > "$marker"
      if [ "$attempts" -lt "$INFRA_MAX_RETRIES" ]; then
        delay="$(retry_delay_seconds "$attempts")"
        echo "[fallback-watch] PR #$pr falhou por infraestrutura; retry $attempts/$INFRA_MAX_RETRIES após ${delay}s." >&2
      else
        echo "[fallback-watch] PR #$pr atingiu o limite de $INFRA_MAX_RETRIES falhas transitórias; nenhum falso verde." >&2
      fi
    else
      rm -f "$retry_file"
      printf 'failure\n' > "$marker"
      echo "[fallback-watch] PR #$pr reprovou em teste/gate real; mesmo SHA não será repetido automaticamente." >&2
    fi
  done
}

while :; do
  run_cycle
  [ "$ONCE" -eq 0 ] || break
  sleep "$INTERVAL"
done
