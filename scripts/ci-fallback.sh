#!/usr/bin/env bash
# Fallback autônomo de CI do EJC.
# Executa validação completa em worktree isolado e publica evidência por SHA.
# O gate promovível é Check Run vinculado a GitHub App dedicado; status clássico
# fica apenas informativo e nunca satisfaz branch protection do fallback.
# Não usa GitHub Actions e nunca opera /opt/ejc ou banco de produção.
set -euo pipefail

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

case "$(realpath "$ROOT" 2>/dev/null || printf '%s' "$ROOT")" in
  /opt/ejc|/opt/ejc/*) die "recusado em /opt/ejc (produção)" ;;
esac
[ "${APP_ENV:-}" != "production" ] && [ "${EJC_ENV:-}" != "production" ] \
  || die "ambiente de produção ativo"
[ ! -e /opt/ejc/.deployed_sha ] && [ ! -e /opt/ejc/.env ] \
  || die "host contém marcadores da instalação produtiva /opt/ejc"
[ "$(id -u)" -ne 0 ] || die "fallback promovível não roda como root"
if [ "$POST_STATUS" -eq 1 ] && [ "${EJC_ALLOW_PYTHON_MISMATCH:-0}" = "1" ]; then
  die "EJC_ALLOW_PYTHON_MISMATCH=1 é somente diagnóstico; não pode publicar status promovível"
fi
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -Eq '^(ejc_backend|ejc_worker|ejc_db|ejc_frontend|ejc_redis)$'; then
    die "containers canônicos do EJC ativos; host não é elegível para CI de PR"
  fi
fi

command -v git >/dev/null 2>&1 || die "git ausente"
command -v jq >/dev/null 2>&1 || die "jq ausente"
command -v gh >/dev/null 2>&1 || { [ "$POST_STATUS" -eq 0 ] || die "gh ausente"; }
if [ "$POST_STATUS" -eq 1 ]; then gh auth status >/dev/null 2>&1 || die "gh não autenticado no host"; fi

REPO="${EJC_REPO:-}"
if [ -z "$REPO" ] && [ "$POST_STATUS" -eq 1 ]; then
  REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
fi
[ -n "$REPO" ] || REPO="s2corporativo/ejc"
FALLBACK_APP_ID="${EJC_FALLBACK_APP_ID:-}"
if [ "$POST_STATUS" -eq 1 ]; then
  [[ "$FALLBACK_APP_ID" =~ ^[1-9][0-9]*$ ]] \
    || die "EJC_FALLBACK_APP_ID numérico (>0) é obrigatório para gate promovível"
fi

WORKTREE_PARENT="${EJC_CI_WORKTREE_ROOT:-${HOME}/.cache/ejc-ci-worktrees}"
EVIDENCE_ROOT="${EJC_CI_EVIDENCE_ROOT:-${HOME}/.cache/ejc-ci-evidence}"
mkdir -p "$WORKTREE_PARENT" "$EVIDENCE_ROOT"
chmod 700 "$WORKTREE_PARENT" "$EVIDENCE_ROOT" 2>/dev/null || true

git fetch --quiet origin main || die "não foi possível atualizar origin/main"

HEAD_REF=""
SHA=""
if [ -n "$PR" ]; then
  [ "$POST_STATUS" -eq 1 ] || die "--pr exige gh/status habilitado"
  META="$(gh pr view "$PR" --repo "$REPO" --json headRefName,headRefOid,baseRefName,isDraft,state)"
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

if ! git merge-base --is-ancestor origin/main "$SHA"; then
  die "head $SHA está atrás da main atual; atualize/reconcilie antes de validar"
fi

CONTEXT_BACKEND='EJC Local / Backend'
CONTEXT_EVAL='EJC Local / Eval'
CONTEXT_FRONTEND='EJC Local / Frontend'
CONTEXT_P0='EJC Local / P0 Guard'
CONTEXT_GOV='EJC Local / Governança'
CONTEXT_FULL='EJC Local Full Gate'
STATUS_SYNC_PENDING=0

post_full_check() {
  local state="$1" description="$2" payload result app_id
  [ "$POST_STATUS" -eq 1 ] || return 0
  case "$state" in
    pending)
      payload="$(jq -cn --arg name "$CONTEXT_FULL" --arg sha "$SHA" --arg summary "${description:0:60000}" '{name:$name, head_sha:$sha, status:"in_progress", output:{title:$name,summary:$summary}}')"
      ;;
    success|failure)
      payload="$(jq -cn --arg name "$CONTEXT_FULL" --arg sha "$SHA" --arg conclusion "$state" --arg summary "${description:0:60000}" '{name:$name, head_sha:$sha, status:"completed", conclusion:$conclusion, output:{title:$name,summary:$summary}}')"
      ;;
    *) die "estado inválido de check: $state" ;;
  esac
  if ! result="$(printf '%s' "$payload" | gh api -X POST "repos/$REPO/check-runs" -H 'Accept: application/vnd.github+json' --input - 2>/dev/null)"; then
    STATUS_SYNC_PENDING=1
    warn "não foi possível publicar Check Run '$CONTEXT_FULL=$state'; evidência local será preservada"
    return 0
  fi
  app_id="$(printf '%s' "$result" | jq -r '.app.id // -1')"
  if [ "$app_id" != "$FALLBACK_APP_ID" ]; then
    STATUS_SYNC_PENDING=1
    warn "Check Run emitido por app_id=$app_id, esperado=$FALLBACK_APP_ID; gate não será aceito"
    return 0
  fi
}

post_status() {
  local state="$1" context="$2" description="$3"
  [ "$POST_STATUS" -eq 1 ] || return 0
  if [ "$context" = "$CONTEXT_FULL" ]; then
    post_full_check "$state" "$description"
    return 0
  fi
  if ! gh api -X POST "repos/$REPO/statuses/$SHA" \
      -f state="$state" -f context="$context" -f description="${description:0:135}" >/dev/null 2>&1; then
    STATUS_SYNC_PENDING=1
    warn "não foi possível publicar status informativo '$context=$state'; evidência local será preservada"
  fi
  return 0
}

publish_success_statuses() {
  for c in "$CONTEXT_BACKEND" "$CONTEXT_EVAL" "$CONTEXT_FRONTEND" "$CONTEXT_P0" "$CONTEXT_GOV"; do
    post_status success "$c" "validado pelo fallback local isolado"
  done
  post_full_check success "todos os gates locais completos aprovados"
}

full_gate_is_green() {
  [ "$POST_STATUS" -eq 1 ] || return 1
  local checks
  checks="$(gh api "repos/$REPO/commits/$SHA/check-runs?per_page=100" 2>/dev/null)" || return 1
  printf '%s' "$checks" | jq -e --arg c "$CONTEXT_FULL" --argjson app_id "$FALLBACK_APP_ID" '
    [.check_runs[] | select(.name == $c and .app.id == $app_id and .conclusion == "success")] | length > 0
  ' >/dev/null 2>&1
}

local_evidence_is_green() {
  local summary="$EVIDENCE_ROOT/$SHA/summary.json"
  [ -s "$summary" ] || return 1
  jq -e --arg sha "$SHA" '.target_sha == $sha and .result == "success"' "$summary" >/dev/null 2>&1
}

revalidate_governance_for_merge() {
  [ -n "$PR" ] || return 1
  local gov_parent gov_work rc
  gov_parent="$WORKTREE_PARENT/merge-governance"
  mkdir -p "$gov_parent"
  gov_work="$gov_parent/${SHA:0:12}-$$"
  [ ! -e "$gov_work" ] || die "worktree temporário de governança já existe: $gov_work"
  git worktree add --detach "$gov_work" "$SHA" >/dev/null
  set +e
  (cd "$gov_work" && EJC_PR_NUMBER="$PR" EJC_GOV_REQUIRE_PR=1 \
    bash scripts/governanca/ci-local-governanca.sh) >/dev/null 2>&1
  rc=$?
  set -e
  git worktree remove --force "$gov_work" >/dev/null 2>&1 || true
  return "$rc"
}

refresh_status_from_evidence() {
  [ -n "$PR" ] || return 1
  if ! local_evidence_is_green; then
    log "Evidência local completa do SHA exato ausente; status não promovido."
    return 1
  fi
  if ! revalidate_governance_for_merge; then
    post_status failure "$CONTEXT_GOV" "governança atual do PR reprovada"
    post_full_check failure "governança atual do PR reprovada"
    log "Governança atual do PR #$PR reprovada; status/merge retidos sem repetir a suíte pesada."
    return 1
  fi
  publish_success_statuses
  if ! full_gate_is_green; then
    log "Check Run remoto do GitHub App esperado ainda indisponível/não verde; será reavaliado depois."
    return 1
  fi
  return 0
}

attempt_merge() {
  [ "$DO_MERGE" -eq 1 ] && [ -n "$PR" ] || return 0
  refresh_status_from_evidence || return 0

  local info labels arqs migs patch
  info="$(gh pr view "$PR" --repo "$REPO" --json isDraft,mergeStateStatus,reviewDecision,labels,headRefOid)"
  [ "$(printf '%s' "$info" | jq -r .headRefOid)" = "$SHA" ] || die "head do PR mudou após a validação"
  [ "$(printf '%s' "$info" | jq -r .isDraft)" = "false" ] || { log "PR #$PR em draft; não mesclado."; return 0; }
  labels="$(printf '%s' "$info" | jq -r '[.labels[].name] | join(",")')"
  case ",$labels," in *,retencao-humana,*) log "PR #$PR com retenção humana; não mesclado."; return 0;; esac

  arqs="$(gh pr diff "$PR" --repo "$REPO" --name-only)"
  local excecao='^(\.github/|\.claude/|CLAUDE\.md|AGENTS\.md|docs/GOVERNANCA|nginx/|docker-compose[^/]*\.yml|scripts/|.*Dockerfile[^/]*$|backend/requirements[^/]*\.txt|frontend/package(-lock)?\.json|frontend/nginx|backend/app/core/|backend/app/middleware|backend/app/routers/(auth|users|api_keys)|backend/app/services/(pii_crypto|ai_gateway)|(^|/)\.env)'
  if printf '%s\n' "$arqs" | grep -Eq "$excecao"; then
    log "PR #$PR toca caminho de exceção §6-A; validação concluída, merge retido."
    return 0
  fi
  migs="$(printf '%s\n' "$arqs" | grep -E '^backend/alembic/versions/' || true)"
  if [ -n "$migs" ]; then
    patch="$(gh pr diff "$PR" --repo "$REPO" || true)"
    if printf '%s' "$patch" | grep -Eiq 'op\.drop_|op\.alter_column|DROP (TABLE|COLUMN|INDEX|CONSTRAINT)|TRUNCATE|DELETE FROM'; then
      log "PR #$PR contém migration potencialmente destrutiva; merge retido."
      return 0
    fi
  fi

  set +e
  local merge_json rc merged message
  merge_json="$(gh api -X PUT "repos/$REPO/pulls/$PR/merge" -f merge_method=squash -f sha="$SHA" 2>&1)"
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    log "PR #$PR ainda não elegível ao merge (review/protection/conflito). Será reavaliado sem repetir o CI do mesmo SHA."
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

WORKTREE="$WORKTREE_PARENT/${SHA:0:12}-$$"
EVIDENCE="$EVIDENCE_ROOT/$SHA"
mkdir -p "$EVIDENCE"; chmod 700 "$EVIDENCE" 2>/dev/null || true

cleanup() {
  set +e
  if git worktree list --porcelain | grep -Fqx "worktree $WORKTREE"; then
    git worktree remove --force "$WORKTREE" >/dev/null 2>&1
  fi
}
trap cleanup EXIT

git worktree add --detach "$WORKTREE" "$SHA" >/dev/null

for c in "$CONTEXT_BACKEND" "$CONTEXT_EVAL" "$CONTEXT_FRONTEND" "$CONTEXT_P0" "$CONTEXT_GOV"; do
  post_status pending "$c" "CI local isolado em execução"
done
post_full_check pending "CI local isolado em execução"

run_stage() {
  local key="$1" context="$2"; shift 2
  local logfile="$EVIDENCE/${key}.log"
  log "Executando $key…"
  set +e
  (cd "$WORKTREE" && "$@") >"$logfile" 2>&1
  local rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    post_status failure "$context" "fallback local falhou: $key (exit $rc)"
    post_full_check failure "fallback local falhou: $key (exit $rc)"
    tail -n 120 "$logfile" >&2 || true
    return "$rc"
  fi
  return 0
}

run_stage backend "$CONTEXT_BACKEND" env EJC_ALLOW_PYTHON_MISMATCH=0 bash scripts/ci-local.sh backend || exit 1
run_stage eval "$CONTEXT_EVAL" env CI_SKIP_PIP=1 EJC_ALLOW_PYTHON_MISMATCH=0 bash scripts/ci-local.sh eval || exit 1
run_stage frontend "$CONTEXT_FRONTEND" bash scripts/ci-local.sh frontend || exit 1
run_stage p0 "$CONTEXT_P0" bash scripts/ci-local.sh p0 || exit 1
if [ -n "$PR" ]; then
  run_stage governanca "$CONTEXT_GOV" env EJC_PR_NUMBER="$PR" EJC_GOV_REQUIRE_PR=1 bash scripts/governanca/ci-local-governanca.sh || exit 1
else
  run_stage governanca "$CONTEXT_GOV" env EJC_GOV_REQUIRE_PR=0 bash scripts/governanca/ci-local-governanca.sh || exit 1
fi
run_stage architecture "$CONTEXT_FULL" bash scripts/ci-local.sh architecture || exit 1
run_stage continuity "$CONTEXT_FULL" env CI_SKIP_PIP=1 EJC_ALLOW_PYTHON_MISMATCH=0 bash scripts/ci-local.sh continuity || exit 1
run_stage ui-extra "$CONTEXT_FULL" bash scripts/ci-local.sh ui-extra || exit 1

python3 - "$EVIDENCE" "$SHA" "$HEAD_REF" "$PR" <<'PY'
from __future__ import annotations
import hashlib, json, pathlib, sys
from datetime import datetime, timezone
root = pathlib.Path(sys.argv[1])
obj = {
    "schema": 1,
    "target_sha": sys.argv[2],
    "ref": sys.argv[3],
    "pr": int(sys.argv[4]) if sys.argv[4] else None,
    "completed_at": datetime.now(timezone.utc).isoformat(),
    "result": "success",
    "logs": {},
}
for p in sorted(root.glob("*.log")):
    obj["logs"][p.name] = {
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        "bytes": p.stat().st_size,
    }
(root / "summary.json").write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY

if [ -n "$PR" ] && ! revalidate_governance_for_merge; then
  post_status failure "$CONTEXT_GOV" "governança atual do PR reprovada"
  post_full_check failure "governança atual do PR reprovada"
  die "governança do PR mudou/reprovou após a suíte"
fi

publish_success_statuses
log "Fallback completo aprovado para $SHA. Evidência local: $EVIDENCE/summary.json"
[ "$STATUS_SYNC_PENDING" -eq 0 ] || warn "um ou mais sinais não sincronizaram; watcher tentará novamente sem repetir a suíte"

attempt_merge
