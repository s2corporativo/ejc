#!/usr/bin/env bash
# Control plane do fallback autônomo do EJC.
# Código do PR nunca executa neste UID: stages de aplicação são delegados ao
# ci-worker-isolation.sh sob usuário Unix dedicado e snapshot novo por stage.
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PR=""
REF=""
DO_MERGE=0
MERGE_ONLY=0
PROMOTE_ONLY=0
POST_STATUS=1
while [ "$#" -gt 0 ]; do
  case "$1" in
    --pr) PR="${2:-}"; shift 2 ;;
    --ref) REF="${2:-}"; shift 2 ;;
    --merge) DO_MERGE=1; shift ;;
    --merge-only) DO_MERGE=1; MERGE_ONLY=1; shift ;;
    --promote-only) PROMOTE_ONLY=1; shift ;;
    --no-status) POST_STATUS=0; shift ;;
    *) echo "uso: $0 [--pr N|--ref REF] [--merge|--merge-only|--promote-only] [--no-status]" >&2; exit 2 ;;
  esac
done

log() { printf '\n[fallback-ci] %s\n' "$*"; }
warn() { printf '[fallback-ci] AVISO: %s\n' "$*" >&2; }
die() { printf '[fallback-ci] ERRO: %s\n' "$*" >&2; exit 1; }

canon() {
  if command -v realpath >/dev/null 2>&1; then realpath -m "$1"; else printf '%s\n' "$1"; fi
}

assert_state_path() {
  local path="$1" label="$2" resolved root_resolved home_resolved
  resolved="$(canon "$path")"
  root_resolved="$(canon "$ROOT")"
  home_resolved="$(canon "${HOME:-/__no_home__}")"
  case "$resolved" in
    /|"$home_resolved"|/opt/ejc|/opt/ejc/*|"$root_resolved"|"$root_resolved"/*)
      die "$label deve ficar fora do repositório, HOME raiz e /opt/ejc: $resolved"
      ;;
  esac
}

case "$(canon "$ROOT")" in
  /opt/ejc|/opt/ejc/*) die "recusado em /opt/ejc (produção)" ;;
esac
[ "${APP_ENV:-}" != "production" ] && [ "${EJC_ENV:-}" != "production" ] || die "ambiente de produção ativo"
[ ! -e /opt/ejc/.deployed_sha ] && [ ! -e /opt/ejc/.env ] || die "host contém marcadores da instalação produtiva /opt/ejc"
[ "$(id -u)" -ne 0 ] || die "fallback promovível não roda como root"
if [ "$POST_STATUS" -eq 1 ] && [ "${EJC_ALLOW_PYTHON_MISMATCH:-0}" = "1" ]; then
  die "EJC_ALLOW_PYTHON_MISMATCH=1 é somente diagnóstico; não pode publicar gate promovível"
fi

for cmd in git jq flock python3; do
  command -v "$cmd" >/dev/null 2>&1 || die "$cmd ausente"
done
[ -f "$ROOT/scripts/ci_evidence.py" ] || die "scripts/ci_evidence.py ausente"
[ -f "$ROOT/scripts/ci-worker-isolation.sh" ] || die "scripts/ci-worker-isolation.sh ausente"
command -v gh >/dev/null 2>&1 || { [ "$POST_STATUS" -eq 0 ] || die "gh ausente"; }
if [ "$POST_STATUS" -eq 1 ]; then
  gh auth status >/dev/null 2>&1 || die "gh de usuário não autenticado no control plane"
fi

REPO="${EJC_REPO:-}"
if [ -z "$REPO" ] && [ "$POST_STATUS" -eq 1 ]; then
  REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
fi
[ -n "$REPO" ] || REPO="s2corporativo/ejc"
[[ "$REPO" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || die "EJC_REPO inválido"

FALLBACK_APP_ID="${EJC_FALLBACK_APP_ID:-}"
INSTALLATION_ID="${EJC_FALLBACK_APP_INSTALLATION_ID:-${EJC_FALLBACK_INSTALLATION_ID:-}}"
if [ "$POST_STATUS" -eq 1 ]; then
  [[ "$FALLBACK_APP_ID" =~ ^[1-9][0-9]*$ ]] || die "EJC_FALLBACK_APP_ID numérico (>0) é obrigatório"
  [[ "$INSTALLATION_ID" =~ ^[1-9][0-9]*$ ]] || die "EJC_FALLBACK_APP_INSTALLATION_ID numérico (>0) é obrigatório"
  [ -n "${EJC_FALLBACK_APP_PRIVATE_KEY_FILE:-}" ] || die "EJC_FALLBACK_APP_PRIVATE_KEY_FILE é obrigatório"
  export EJC_FALLBACK_APP_INSTALLATION_ID="$INSTALLATION_ID"
  # shellcheck source=github-app-auth.sh
  source "$ROOT/scripts/github-app-auth.sh"
fi

STATE_ROOT="${EJC_CI_STATE_ROOT:-${XDG_CACHE_HOME:-${HOME:-/tmp}/.cache}/ejc-ci-fallback}"
WORKTREE_PARENT="${EJC_CI_WORKTREE_ROOT:-$STATE_ROOT/worktrees}"
EVIDENCE_ROOT="${EJC_CI_EVIDENCE_ROOT:-$STATE_ROOT/evidence}"
assert_state_path "$STATE_ROOT" "STATE_ROOT"
assert_state_path "$WORKTREE_PARENT" "WORKTREE_PARENT"
assert_state_path "$EVIDENCE_ROOT" "EVIDENCE_ROOT"
mkdir -p "$STATE_ROOT" "$WORKTREE_PARENT" "$EVIDENCE_ROOT"
chmod 700 "$STATE_ROOT" "$WORKTREE_PARENT" "$EVIDENCE_ROOT" 2>/dev/null || true
export EJC_CI_STATE_ROOT="$STATE_ROOT"

# O worker é fronteira de segurança obrigatória, inclusive em promote/merge-only:
# se a configuração perdeu isolamento, nenhuma evidência é republicada.
bash "$ROOT/scripts/ci-worker-isolation.sh" preflight || die "worker isolado não atende aos invariantes de segurança"

git fetch --quiet origin main || die "não foi possível atualizar origin/main"

HEAD_REF=""
SHA=""
if [ -n "$PR" ]; then
  [ "$POST_STATUS" -eq 1 ] || die "--pr exige integração remota habilitada"
  [[ "$PR" =~ ^[1-9][0-9]*$ ]] || die "número de PR inválido"
  META="$(gh pr view "$PR" --repo "$REPO" --json headRefName,headRefOid,baseRefName,isDraft,state)" || die "não foi possível ler metadados do PR #$PR"
  [ "$(printf '%s' "$META" | jq -r .state)" = "OPEN" ] || die "PR #$PR não está aberto"
  [ "$(printf '%s' "$META" | jq -r .baseRefName)" = "main" ] || die "PR #$PR não tem base main"
  HEAD_REF="$(printf '%s' "$META" | jq -r .headRefName)"
  SHA="$(printf '%s' "$META" | jq -r .headRefOid)"
  git fetch --quiet origin "$HEAD_REF" || die "falha ao buscar branch $HEAD_REF"
  [ "$(git rev-parse FETCH_HEAD)" = "$SHA" ] || die "SHA remoto mudou durante a preparação"
elif [ -n "$REF" ]; then
  git fetch --quiet origin "$REF" || true
  SHA="$(git rev-parse "$REF^{commit}" 2>/dev/null || git rev-parse FETCH_HEAD^{commit} 2>/dev/null || true)"
  [ -n "$SHA" ] || die "ref não resolvida: $REF"
  HEAD_REF="$REF"
else
  SHA="$(git rev-parse HEAD)"
  HEAD_REF="$(git branch --show-current || true)"
fi
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || die "SHA alvo inválido: $SHA"
git merge-base --is-ancestor origin/main "$SHA" || die "head $SHA está atrás da main atual; reconcilie antes de validar"

SHA_EVIDENCE="$EVIDENCE_ROOT/$SHA"
mkdir -p "$SHA_EVIDENCE/attempts"
chmod 700 "$SHA_EVIDENCE" "$SHA_EVIDENCE/attempts" 2>/dev/null || true
exec 9>"$SHA_EVIDENCE/.lock"
if ! flock -n 9; then
  warn "já existe validação/promoção ativa para $SHA; operação adiada"
  exit 75
fi

CONTEXT_BACKEND='EJC Local / Backend'
CONTEXT_EVAL='EJC Local / Eval'
CONTEXT_FRONTEND='EJC Local / Frontend'
CONTEXT_P0='EJC Local / P0 Guard'
CONTEXT_GOV='EJC Local / Governança'
CONTEXT_FULL='EJC Local Full Gate'
STATUS_SYNC_PENDING=0
FULL_CHECK_ID=""
FULL_CHECK_EXTERNAL_ID=""
GOV_WORKTREE=""
ATTEMPT_DIR=""

cleanup() {
  set +e
  if [ -n "${GOV_WORKTREE:-}" ] && git worktree list --porcelain | grep -Fqx "worktree $GOV_WORKTREE"; then
    git worktree remove --force "$GOV_WORKTREE" >/dev/null 2>&1 || true
  fi
  if [ "$POST_STATUS" -eq 1 ] && declare -F ejc_github_app_clear >/dev/null 2>&1; then
    ejc_github_app_clear || true
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

preflight_app_credential() {
  [ "$POST_STATUS" -eq 1 ] || return 0
  local name='EJC Local Credential Preflight' payload result app_id head_sha
  payload="$(jq -cn --arg name "$name" --arg sha "$SHA" '{name:$name,head_sha:$sha,status:"completed",conclusion:"neutral",output:{title:$name,summary:"validação da identidade e checks:write do GitHub App antes do gate pesado"}}')"
  if ! result="$(printf '%s' "$payload" | ejc_github_app_gh_api -X POST "repos/$REPO/check-runs" -H 'Accept: application/vnd.github+json' --input - 2>/dev/null)"; then
    die "GitHub App não conseguiu criar Check Run; suíte promovível não iniciada"
  fi
  app_id="$(printf '%s' "$result" | jq -r '.app.id // -1')"
  head_sha="$(printf '%s' "$result" | jq -r '.head_sha // empty')"
  [ "$app_id" = "$FALLBACK_APP_ID" ] || die "Check Run emitido por app_id=$app_id, esperado=$FALLBACK_APP_ID"
  [ "$head_sha" = "$SHA" ] || die "preflight do App retornou SHA diferente do alvo"
  log "Credencial efêmera do GitHub App validada (app_id=$app_id)."
}

post_full_check() {
  local state="$1" description="$2" payload result app_id head_sha name conclusion id external_id
  [ "$POST_STATUS" -eq 1 ] || return 0
  [ -n "$FULL_CHECK_EXTERNAL_ID" ] || FULL_CHECK_EXTERNAL_ID="ejc-fallback:$SHA:promotion:$(date +%s)-$$"

  case "$state" in
    pending)
      payload="$(jq -cn --arg name "$CONTEXT_FULL" --arg sha "$SHA" --arg external_id "$FULL_CHECK_EXTERNAL_ID" --arg summary "${description:0:60000}" '{name:$name,head_sha:$sha,status:"in_progress",external_id:$external_id,output:{title:$name,summary:$summary}}')"
      ;;
    success|failure)
      if [ -n "$FULL_CHECK_ID" ]; then
        payload="$(jq -cn --arg conclusion "$state" --arg summary "${description:0:60000}" '{status:"completed",conclusion:$conclusion,output:{title:"EJC Local Full Gate",summary:$summary}}')"
      else
        payload="$(jq -cn --arg name "$CONTEXT_FULL" --arg sha "$SHA" --arg external_id "$FULL_CHECK_EXTERNAL_ID" --arg conclusion "$state" --arg summary "${description:0:60000}" '{name:$name,head_sha:$sha,status:"completed",conclusion:$conclusion,external_id:$external_id,output:{title:$name,summary:$summary}}')"
      fi
      ;;
    *) die "estado inválido de Check Run: $state" ;;
  esac

  if [ -n "$FULL_CHECK_ID" ] && [ "$state" != "pending" ]; then
    if ! result="$(printf '%s' "$payload" | ejc_github_app_gh_api -X PATCH "repos/$REPO/check-runs/$FULL_CHECK_ID" -H 'Accept: application/vnd.github+json' --input - 2>/dev/null)"; then
      STATUS_SYNC_PENDING=1
      warn "não foi possível atualizar o Check Run atual para '$state'"
      return 75
    fi
  else
    if ! result="$(printf '%s' "$payload" | ejc_github_app_gh_api -X POST "repos/$REPO/check-runs" -H 'Accept: application/vnd.github+json' --input - 2>/dev/null)"; then
      STATUS_SYNC_PENDING=1
      warn "não foi possível criar Check Run '$CONTEXT_FULL=$state'; evidência local preservada"
      return 75
    fi
  fi

  id="$(printf '%s' "$result" | jq -r '.id // empty')"
  app_id="$(printf '%s' "$result" | jq -r '.app.id // -1')"
  head_sha="$(printf '%s' "$result" | jq -r '.head_sha // empty')"
  name="$(printf '%s' "$result" | jq -r '.name // empty')"
  conclusion="$(printf '%s' "$result" | jq -r '.conclusion // empty')"
  external_id="$(printf '%s' "$result" | jq -r '.external_id // empty')"
  [[ "$id" =~ ^[1-9][0-9]*$ ]] || { STATUS_SYNC_PENDING=1; return 75; }
  [ "$app_id" = "$FALLBACK_APP_ID" ] || { STATUS_SYNC_PENDING=1; return 75; }
  [ "$head_sha" = "$SHA" ] || { STATUS_SYNC_PENDING=1; return 75; }
  [ "$name" = "$CONTEXT_FULL" ] || { STATUS_SYNC_PENDING=1; return 75; }
  [ "$external_id" = "$FULL_CHECK_EXTERNAL_ID" ] || { STATUS_SYNC_PENDING=1; return 75; }
  if [ "$state" = "success" ] || [ "$state" = "failure" ]; then
    [ "$conclusion" = "$state" ] || { STATUS_SYNC_PENDING=1; return 75; }
  fi
  FULL_CHECK_ID="$id"
  return 0
}

post_status() {
  local state="$1" context="$2" description="$3"
  [ "$POST_STATUS" -eq 1 ] || return 0
  if ! gh api -X POST "repos/$REPO/statuses/$SHA" \
      -f state="$state" -f context="$context" -f description="${description:0:135}" >/dev/null 2>&1; then
    STATUS_SYNC_PENDING=1
    warn "não foi possível publicar status informativo '$context=$state'; evidência local preservada"
    return 75
  fi
  return 0
}

latest_full_check_id() {
  local checks
  checks="$(ejc_github_app_gh_api --method GET "repos/$REPO/commits/$SHA/check-runs" \
    -H 'Accept: application/vnd.github+json' \
    -f check_name="$CONTEXT_FULL" -F app_id="$FALLBACK_APP_ID" -f filter=latest -F per_page=100 2>/dev/null)" || return 1
  printf '%s' "$checks" | jq -r '.check_runs | sort_by(.id) | last | .id // 0'
}

full_gate_is_green() {
  [ "$POST_STATUS" -eq 1 ] || return 1
  [[ "$FULL_CHECK_ID" =~ ^[1-9][0-9]*$ ]] || return 1
  [ -n "$FULL_CHECK_EXTERNAL_ID" ] || return 1
  local check latest
  check="$(ejc_github_app_gh_api "repos/$REPO/check-runs/$FULL_CHECK_ID" -H 'Accept: application/vnd.github+json' 2>/dev/null)" || return 1
  printf '%s' "$check" | jq -e \
    --arg name "$CONTEXT_FULL" --arg sha "$SHA" --arg external_id "$FULL_CHECK_EXTERNAL_ID" --argjson app_id "$FALLBACK_APP_ID" '
      .name == $name and
      .head_sha == $sha and
      .external_id == $external_id and
      .app.id == $app_id and
      .status == "completed" and
      .conclusion == "success"
    ' >/dev/null 2>&1 || return 1
  latest="$(latest_full_check_id 2>/dev/null || printf '0')"
  [ "$latest" = "$FULL_CHECK_ID" ]
}

publish_success_statuses() {
  local c
  for c in "$CONTEXT_BACKEND" "$CONTEXT_EVAL" "$CONTEXT_FRONTEND" "$CONTEXT_P0" "$CONTEXT_GOV"; do
    post_status success "$c" "validado pelo fallback local isolado" || true
  done
  post_full_check success "todos os gates locais completos aprovados"
}

local_evidence_is_green() {
  python3 "$ROOT/scripts/ci_evidence.py" verify --sha-root "$SHA_EVIDENCE" --sha "$SHA" >/dev/null 2>&1
}

finish_attempt() {
  local result="$1" failed_stage="${2:-}" exit_code="${3:-0}" promote="${4:-0}"
  local args=(finish --attempt "$ATTEMPT_DIR" --sha-root "$SHA_EVIDENCE" --sha "$SHA" --ref "$HEAD_REF" --result "$result" --exit-code "$exit_code")
  [ -z "$PR" ] || args+=(--pr "$PR")
  [ -z "$failed_stage" ] || args+=(--failed-stage "$failed_stage")
  [ "$promote" -eq 0 ] || args+=(--promote)
  python3 "$ROOT/scripts/ci_evidence.py" "${args[@]}" >/dev/null
}

create_governance_worktree() {
  [ -z "$GOV_WORKTREE" ] || return 0
  GOV_WORKTREE="$WORKTREE_PARENT/governance-${SHA:0:12}-$$"
  [ ! -e "$GOV_WORKTREE" ] || die "worktree temporário de governança já existe: $GOV_WORKTREE"
  git worktree add --detach "$GOV_WORKTREE" "$SHA" >/dev/null
}

run_governance() {
  local logfile="$1" rc
  create_governance_worktree
  set +e
  EJC_GOV_SOURCE_ROOT="$GOV_WORKTREE" EJC_PR_NUMBER="$PR" EJC_GOV_REQUIRE_PR=1 \
    bash "$ROOT/scripts/governanca/ci-local-governanca.sh" >"$logfile" 2>&1
  rc=$?
  set -e
  return "$rc"
}

revalidate_governance_for_merge() {
  [ -n "$PR" ] || return 1
  local tmp="$STATE_ROOT/governance-revalidate-${SHA:0:12}-$$.log" rc
  set +e
  run_governance "$tmp"
  rc=$?
  set -e
  rm -f "$tmp"
  return "$rc"
}

refresh_status_from_evidence() {
  [ -n "$PR" ] || return 1
  if ! local_evidence_is_green; then
    log "Evidência local completa, atual e íntegra do SHA exato ausente; status não promovido."
    return 1
  fi
  if ! revalidate_governance_for_merge; then
    post_status failure "$CONTEXT_GOV" "governança atual do PR reprovada" || true
    log "Governança atual do PR #$PR reprovada; promoção retida."
    return 1
  fi
  FULL_CHECK_ID=""
  FULL_CHECK_EXTERNAL_ID="ejc-fallback:$SHA:promotion:$(date +%s)-$$"
  if ! publish_success_statuses; then
    log "Evidência local verde, mas Check Run canônico não sincronizou; merge retido."
    return 1
  fi
  if ! full_gate_is_green; then
    log "Check Run exato/mais recente desta promoção não ficou verde; merge retido."
    return 1
  fi
  return 0
}

verify_branch_protection_for_merge() {
  local protection
  protection="$(gh api "repos/$REPO/branches/main/protection" 2>/dev/null)" || return 1
  printf '%s' "$protection" | jq -e --arg name "$CONTEXT_FULL" --argjson app_id "$FALLBACK_APP_ID" '
    .required_status_checks.strict == true and
    any(.required_status_checks.checks[]?; .context == $name and .app_id == $app_id) and
    .enforce_admins.enabled == true and
    (.required_pull_request_reviews.required_approving_review_count // 0) >= 1 and
    .required_pull_request_reviews.require_code_owner_reviews == true and
    .required_pull_request_reviews.require_last_push_approval == true and
    .required_conversation_resolution.enabled == true and
    .required_linear_history.enabled == true and
    .allow_force_pushes.enabled == false and
    .allow_deletions.enabled == false
  ' >/dev/null 2>&1
}

verify_merge_snapshot() {
  local info review_decision labels
  git fetch --quiet origin main || return 1
  git merge-base --is-ancestor origin/main "$SHA" || return 1
  local_evidence_is_green || return 1
  full_gate_is_green || return 1
  verify_branch_protection_for_merge || return 1
  info="$(gh pr view "$PR" --repo "$REPO" --json isDraft,reviewDecision,labels,headRefOid,state)" || return 1
  [ "$(printf '%s' "$info" | jq -r .state)" = "OPEN" ] || return 1
  [ "$(printf '%s' "$info" | jq -r .headRefOid)" = "$SHA" ] || return 1
  [ "$(printf '%s' "$info" | jq -r .isDraft)" = "false" ] || return 1
  review_decision="$(printf '%s' "$info" | jq -r '.reviewDecision // ""')"
  [ "$review_decision" = "APPROVED" ] || return 1
  labels="$(printf '%s' "$info" | jq -r '[.labels[].name] | join(",")')"
  case ",$labels," in *,retencao-humana,*) return 1;; esac
  return 0
}

attempt_merge() {
  [ "$DO_MERGE" -eq 1 ] && [ -n "$PR" ] || return 0
  refresh_status_from_evidence || return 0
  verify_merge_snapshot || { log "snapshot final reprovado; merge retido"; return 0; }

  local files_json excecao
  if ! files_json="$(gh api --paginate "repos/$REPO/pulls/$PR/files?per_page=100" 2>/dev/null | jq -s 'add')"; then
    log "lista/diff de arquivos do PR indisponível; merge retido fail-closed"
    return 0
  fi
  printf '%s' "$files_json" | jq -e 'type == "array"' >/dev/null 2>&1 || { log "resposta inválida ao listar arquivos; merge retido"; return 0; }

  excecao='^(\.github/|\.claude/|CLAUDE\.md$|AGENTS\.md$|docs/GOVERNANCA|nginx/|docker-compose[^/]*\.yml$|scripts/|.*Dockerfile[^/]*$|backend/requirements[^/]*\.txt$|frontend/package(-lock)?\.json$|frontend/nginx|backend/app/core/|backend/app/middleware|backend/app/routers/(auth|users|api_keys)|backend/app/services/(pii_crypto|ai_gateway)|(^|/)\.env)'
  if printf '%s' "$files_json" | jq -e --arg re "$excecao" '[.[] | select(.filename | test($re))] | length > 0' >/dev/null; then
    log "PR #$PR toca caminho de exceção §6-A; validação concluída, merge retido."
    return 0
  fi

  if printf '%s' "$files_json" | jq -e '[.[] | select(.filename | startswith("backend/alembic/versions/"))] | length > 0' >/dev/null; then
    if printf '%s' "$files_json" | jq -e '[.[] | select(.filename | startswith("backend/alembic/versions/")) | select(.patch == null)] | length > 0' >/dev/null; then
      log "migration com patch indisponível/truncado; merge retido fail-closed"
      return 0
    fi
    if printf '%s' "$files_json" | jq -r '.[] | select(.filename | startswith("backend/alembic/versions/")) | .patch' \
      | grep -Eiq 'op\.drop_|op\.alter_column|DROP (TABLE|COLUMN|INDEX|CONSTRAINT)|TRUNCATE|DELETE FROM'; then
      log "PR #$PR contém migration potencialmente destrutiva; merge retido."
      return 0
    fi
  fi

  # Minimiza TOCTOU: repete todos os invariantes remotos/local imediatamente
  # antes do ato; o próprio endpoint também recebe o SHA esperado.
  verify_merge_snapshot || { log "estado mudou imediatamente antes do merge; retido"; return 0; }

  set +e
  local merge_json rc merged message
  merge_json="$(gh api -X PUT "repos/$REPO/pulls/$PR/merge" -f merge_method=squash -f sha="$SHA" 2>&1)"
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    log "PR #$PR ainda não elegível ao merge (review/protection/conflito); será reavaliado sem repetir CI do mesmo SHA."
    return 0
  fi
  merged="$(printf '%s' "$merge_json" | jq -r '.merged // false' 2>/dev/null || echo false)"
  message="$(printf '%s' "$merge_json" | jq -r '.message // ""' 2>/dev/null || true)"
  if [ "$merged" = "true" ]; then
    log "PR #$PR integrado após fallback local completo."
  else
    log "PR #$PR não integrado: ${message:-proteção/review pendente}."
  fi
}

run_worker_stage() {
  local key="$1" context="$2" logfile="$ATTEMPT_DIR/${key}.log" rc
  log "Executando $key no worker isolado…"
  set +e
  EJC_CI_WORKER_USER="${EJC_CI_WORKER_USER:-}" \
    EJC_CI_WORKER_ROOT="${EJC_CI_WORKER_ROOT:-/var/tmp/ejc-ci-worker}" \
    EJC_FALLBACK_APP_PRIVATE_KEY_FILE="${EJC_FALLBACK_APP_PRIVATE_KEY_FILE:-}" \
    EJC_CI_STATE_ROOT="$STATE_ROOT" \
    bash "$ROOT/scripts/ci-worker-isolation.sh" run-stage --sha "$SHA" --stage "$key" >"$logfile" 2>&1
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    finish_attempt failure "$key" "$rc" 0 || true
    post_status failure "$context" "fallback local falhou: $key (exit $rc)" || true
    post_full_check failure "fallback local falhou: $key (exit $rc)" || true
    tail -n 120 "$logfile" >&2 || true
    return "$rc"
  fi
  return 0
}

run_governance_stage() {
  local logfile="$ATTEMPT_DIR/governanca.log" rc
  log "Executando governança trusted contra snapshot do PR…"
  set +e
  run_governance "$logfile"
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    finish_attempt failure "governanca" "$rc" 0 || true
    post_status failure "$CONTEXT_GOV" "governança falhou (exit $rc)" || true
    post_full_check failure "governança falhou (exit $rc)" || true
    tail -n 120 "$logfile" >&2 || true
    return "$rc"
  fi
  return 0
}

preflight_app_credential

if [ "$PROMOTE_ONLY" -eq 1 ]; then
  [ -n "$PR" ] || die "--promote-only exige --pr"
  refresh_status_from_evidence
  exit $?
fi

if [ "$MERGE_ONLY" -eq 1 ]; then
  [ -n "$PR" ] || die "--merge-only exige --pr"
  attempt_merge
  exit 0
fi

START_ARGS=(start --root "$EVIDENCE_ROOT" --sha "$SHA" --ref "$HEAD_REF")
[ -z "$PR" ] || START_ARGS+=(--pr "$PR")
ATTEMPT_DIR="$(python3 "$ROOT/scripts/ci_evidence.py" "${START_ARGS[@]}")" || die "não foi possível iniciar tentativa de evidência"
FULL_CHECK_EXTERNAL_ID="ejc-fallback:$SHA:$(basename "$ATTEMPT_DIR")"

for c in "$CONTEXT_BACKEND" "$CONTEXT_EVAL" "$CONTEXT_FRONTEND" "$CONTEXT_P0" "$CONTEXT_GOV"; do
  post_status pending "$c" "CI local isolado em execução" || true
done
post_full_check pending "CI local isolado em execução" || true

run_worker_stage backend "$CONTEXT_BACKEND" || exit 1
run_worker_stage eval "$CONTEXT_EVAL" || exit 1
run_worker_stage frontend "$CONTEXT_FRONTEND" || exit 1
run_worker_stage p0 "$CONTEXT_P0" || exit 1
run_governance_stage || exit 1
run_worker_stage architecture "$CONTEXT_FULL" || exit 1
run_worker_stage continuity "$CONTEXT_FULL" || exit 1
run_worker_stage ui-extra "$CONTEXT_FULL" || exit 1

finish_attempt success "" 0 1

if [ -n "$PR" ] && ! revalidate_governance_for_merge; then
  post_status failure "$CONTEXT_GOV" "governança atual do PR reprovada" || true
  post_full_check failure "governança atual do PR reprovada" || true
  die "governança do PR mudou/reprovou após a suíte"
fi

if publish_success_statuses && full_gate_is_green; then
  log "Fallback completo aprovado para $SHA. Evidência local atual: $SHA_EVIDENCE/latest-success.json"
else
  STATUS_SYNC_PENDING=1
  warn "suíte local aprovada, mas Check Run canônico não sincronizou; merge permanece bloqueado"
fi
[ "$STATUS_SYNC_PENDING" -eq 0 ] || warn "um ou mais sinais remotos não sincronizaram; watcher poderá republicar sem repetir a suíte"

attempt_merge
