#!/usr/bin/env bash
# Fallback autônomo de CI do EJC.
# Executa validação completa em worktree isolado e publica status por SHA.
# Não usa GitHub Actions e nunca opera /opt/ejc ou banco de produção.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PR=""
REF=""
DO_MERGE=0
MERGE_ONLY=0
POST_STATUS=1
while [ "$#" -gt 0 ]; do
  case "$1" in
    --pr) PR="${2:-}"; shift 2 ;;
    --ref) REF="${2:-}"; shift 2 ;;
    --merge) DO_MERGE=1; shift ;;
    --merge-only) DO_MERGE=1; MERGE_ONLY=1; shift ;;
    --no-status) POST_STATUS=0; shift ;;
    *) echo "uso: $0 [--pr N|--ref REF] [--merge|--merge-only] [--no-status]" >&2; exit 2 ;;
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

CONTEXT_BACKEND='Backend — suíte completa + schema/RAG (Postgres pgvector)'
CONTEXT_EVAL='Eval — smoke dos gold sets (offline, bloqueante)'
CONTEXT_FRONTEND='Frontend — testes + typecheck + build'
CONTEXT_P0='P0 guard — conflitos e segredos'
CONTEXT_GOV='Governança — travas de PR'
CONTEXT_FULL='EJC Local Full Gate'
STATUS_SYNC_PENDING=0

post_status() {
  local state="$1" context="$2" description="$3"
  [ "$POST_STATUS" -eq 1 ] || return 0
  if ! gh api -X POST "repos/$REPO/statuses/$SHA" \
      -f state="$state" -f context="$context" -f description="${description:0:135}" >/dev/null 2>&1; then
    STATUS_SYNC_PENDING=1
    warn "não foi possível publicar status '$context=$state'; evidência local será preservada para nova tentativa"
  fi
  return 0
}

publish_success_statuses() {
  for c in "$CONTEXT_BACKEND" "$CONTEXT_EVAL" "$CONTEXT_FRONTEND" "$CONTEXT_P0" "$CONTEXT_GOV"; do
    post_status success "$c" "validado pelo fallback local isolado"
  done
  post_status success "$CONTEXT_FULL" "todos os gates locais completos aprovados"
}

full_gate_is_green() {
  [ "$POST_STATUS" -eq 1 ] || return 1
  local status_json state
  status_json="$(gh api "repos/$REPO/commits/$SHA/status" 2>/dev/null)" || return 1
  state="$(printf '%s' "$status_json" | jq -r --arg c "$CONTEXT_FULL" '[.statuses[] | select(.context == $c)][0].state // ""')"
  [ "$state" = "success" ]
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

attempt_merge() {
  [ "$DO_MERGE" -eq 1 ] && [ -n "$PR" ] || return 0
  if ! local_evidence_is_green; then
    log "Evidência local completa do SHA exato ausente; merge não tentado."
    return 0
  fi

  # Metadados do PR podem mudar sem novo SHA. Revalide governança em toda
  # tentativa de merge para não herdar autorização de uma descrição antiga.
  if ! revalidate_governance_for_merge; then
    post_status failure "$CONTEXT_GOV" "governança atual do PR reprovada"
    post_status failure "$CONTEXT_FULL" "governança atual do PR reprovada"
    log "Governança atual do PR #$PR reprovada; merge retido sem repetir a suíte pesada."
    return 0
  fi

  # Se a API/status caiu durante a suíte, a evidência local continua válida.
  # Re-publicamos o mesmo resultado somente depois da governança atual passar.
  publish_success_statuses
  full_gate_is_green || { log "status remoto ainda indisponível/não verde; merge será reavaliado depois."; return 0; }

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

for c in "$CONTEXT_BACKEND" "$CONTEXT_EVAL" "$CONTEXT_FRONTEND" "$CONTEXT_P0" "$CONTEXT_GOV" "$CONTEXT_FULL"; do
  post_status pending "$c" "CI local isolado em execução"
done

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
    post_status failure "$CONTEXT_FULL" "fallback local falhou: $key (exit $rc)"
    tail -n 120 "$logfile" >&2 || true
    return "$rc"
  fi
  return 0
}

# Para execução promovível, Python divergente nunca é propagado. Os cinco
# contexts só ficam verdes após TODOS os extras e a governança do PR atual.
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

# Revalida metadados uma vez mais imediatamente antes de promover o status.
if [ -n "$PR" ] && ! revalidate_governance_for_merge; then
  post_status failure "$CONTEXT_GOV" "governança atual do PR reprovada"
  post_status failure "$CONTEXT_FULL" "governança atual do PR reprovada"
  die "governança do PR mudou/reprovou após a suíte"
fi

publish_success_statuses
log "Fallback completo aprovado para $SHA. Evidência local: $EVIDENCE/summary.json"
[ "$STATUS_SYNC_PENDING" -eq 0 ] || warn "um ou mais statuses não sincronizaram; watcher tentará novamente sem repetir a suíte"

attempt_merge
