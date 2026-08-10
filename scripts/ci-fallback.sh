#!/usr/bin/env bash
# Fallback autônomo de CI do EJC.
# Executa validação completa em worktree isolado e publica evidência por SHA.
# O gate promovível é um Check Run vinculado a GitHub App dedicado; status
# clássico fica apenas informativo e nunca satisfaz branch protection.
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

canon() {
  if command -v realpath >/dev/null 2>&1; then realpath -m "$1"; else printf '%s\n' "$1"; fi
}

assert_state_path() {
  local path="$1" label="$2" resolved root_resolved
  resolved="$(canon "$path")"
  root_resolved="$(canon "$ROOT")"
  case "$resolved" in
    /|"${HOME:-/__no_home__}"|/opt/ejc|/opt/ejc/*|"$root_resolved"|"$root_resolved"/*)
      die "$label deve ficar fora do repositório, HOME raiz e /opt/ejc: $resolved"
      ;;
  esac
}

case "$(canon "$ROOT")" in
  /opt/ejc|/opt/ejc/*) die "recusado em /opt/ejc (produção)" ;;
esac
[ "${APP_ENV:-}" != "production" ] && [ "${EJC_ENV:-}" != "production" ] \
  || die "ambiente de produção ativo"
[ ! -e /opt/ejc/.deployed_sha ] && [ ! -e /opt/ejc/.env ] \
  || die "host contém marcadores da instalação produtiva /opt/ejc"
[ "$(id -u)" -ne 0 ] || die "fallback promovível não roda como root"
if [ "$POST_STATUS" -eq 1 ] && [ "${EJC_ALLOW_PYTHON_MISMATCH:-0}" = "1" ]; then
  die "EJC_ALLOW_PYTHON_MISMATCH=1 é somente diagnóstico; não pode publicar gate promovível"
fi

for cmd in git jq flock python3; do
  command -v "$cmd" >/dev/null 2>&1 || die "$cmd ausente"
done
command -v gh >/dev/null 2>&1 || { [ "$POST_STATUS" -eq 0 ] || die "gh ausente"; }
if [ "$POST_STATUS" -eq 1 ]; then
  gh auth status >/dev/null 2>&1 || die "gh de usuário não autenticado no host"
  command -v docker >/dev/null 2>&1 || die "Docker é obrigatório para fallback promovível"
  docker info >/dev/null 2>&1 || die "Docker não acessível; fallback promovível exige PostgreSQL efêmero hermético"
fi
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -Eq '^(ejc_backend|ejc_worker|ejc_db|ejc_frontend|ejc_redis)$'; then
    die "containers canônicos do EJC ativos; host não é elegível para CI de PR"
  fi
fi

REPO="${EJC_REPO:-}"
if [ -z "$REPO" ] && [ "$POST_STATUS" -eq 1 ]; then
  REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
fi
[ -n "$REPO" ] || REPO="s2corporativo/ejc"
FALLBACK_APP_ID="${EJC_FALLBACK_APP_ID:-}"
if [ "$POST_STATUS" -eq 1 ]; then
  [[ "$FALLBACK_APP_ID" =~ ^[1-9][0-9]*$ ]] \
    || die "EJC_FALLBACK_APP_ID numérico (>0) é obrigatório para gate promovível"
  [ -n "${EJC_FALLBACK_INSTALLATION_ID:-}" ] \
    || die "EJC_FALLBACK_INSTALLATION_ID é obrigatório para renovar a credencial do App"
  [ -n "${EJC_FALLBACK_APP_PRIVATE_KEY_FILE:-}" ] \
    || die "EJC_FALLBACK_APP_PRIVATE_KEY_FILE é obrigatório para renovar a credencial do App"
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

git fetch --quiet origin main || die "não foi possível atualizar origin/main"

HEAD_REF=""
SHA=""
if [ -n "$PR" ]; then
  [ "$POST_STATUS" -eq 1 ] || die "--pr exige gh/status habilitado"
  META="$(gh pr view "$PR" --repo "$REPO" --json headRefName,headRefOid,baseRefName,isDraft,state)" \
    || die "não foi possível ler metadados do PR #$PR"
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

if ! git merge-base --is-ancestor origin/main "$SHA"; then
  die "head $SHA está atrás da main atual; atualize/reconcilie antes de validar"
fi

SHA_EVIDENCE="$EVIDENCE_ROOT/$SHA"
mkdir -p "$SHA_EVIDENCE/attempts"
chmod 700 "$SHA_EVIDENCE" "$SHA_EVIDENCE/attempts" 2>/dev/null || true
LOCK_FILE="$SHA_EVIDENCE/.lock"
exec 9>"$LOCK_FILE"
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
GOV_WORKTREE=""
WORKTREE=""
ATTEMPT_DIR=""
ATTEMPT_ID=""

cleanup_worktrees() {
  set +e
  if [ -n "${GOV_WORKTREE:-}" ] && git worktree list --porcelain | grep -Fqx "worktree $GOV_WORKTREE"; then
    git worktree remove --force "$GOV_WORKTREE" >/dev/null 2>&1 || true
  fi
  if [ -n "${WORKTREE:-}" ] && git worktree list --porcelain | grep -Fqx "worktree $WORKTREE"; then
    git worktree remove --force "$WORKTREE" >/dev/null 2>&1 || true
  fi
  if [ "$POST_STATUS" -eq 1 ] && declare -F ejc_github_app_clear >/dev/null 2>&1; then
    ejc_github_app_clear || true
  fi
}
trap cleanup_worktrees EXIT INT TERM HUP

preflight_app_credential() {
  [ "$POST_STATUS" -eq 1 ] || return 0
  local name='EJC Local Credential Preflight' payload result app_id head_sha
  payload="$(jq -cn --arg name "$name" --arg sha "$SHA" '{name:$name,head_sha:$sha,status:"completed",conclusion:"neutral",output:{title:$name,summary:"validação da identidade do GitHub App antes do gate pesado"}}')"
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
  local state="$1" description="$2" payload result app_id head_sha name conclusion id
  [ "$POST_STATUS" -eq 1 ] || return 0

  case "$state" in
    pending)
      payload="$(jq -cn --arg name "$CONTEXT_FULL" --arg sha "$SHA" --arg summary "${description:0:60000}" '{name:$name,head_sha:$sha,status:"in_progress",output:{title:$name,summary:$summary}}')"
      ;;
    success|failure)
      if [ -n "$FULL_CHECK_ID" ]; then
        payload="$(jq -cn --arg conclusion "$state" --arg summary "${description:0:60000}" '{status:"completed",conclusion:$conclusion,output:{title:"EJC Local Full Gate",summary:$summary}}')"
      else
        payload="$(jq -cn --arg name "$CONTEXT_FULL" --arg sha "$SHA" --arg conclusion "$state" --arg summary "${description:0:60000}" '{name:$name,head_sha:$sha,status:"completed",conclusion:$conclusion,output:{title:$name,summary:$summary}}')"
      fi
      ;;
    *) die "estado inválido de Check Run: $state" ;;
  esac

  if [ -n "$FULL_CHECK_ID" ] && [ "$state" != "pending" ]; then
    if ! result="$(printf '%s' "$payload" | ejc_github_app_gh_api -X PATCH "repos/$REPO/check-runs/$FULL_CHECK_ID" -H 'Accept: application/vnd.github+json' --input - 2>/dev/null)"; then
      STATUS_SYNC_PENDING=1
      FULL_CHECK_ID=""
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
  [[ "$id" =~ ^[1-9][0-9]*$ ]] || { STATUS_SYNC_PENDING=1; FULL_CHECK_ID=""; return 75; }
  [ "$app_id" = "$FALLBACK_APP_ID" ] || { STATUS_SYNC_PENDING=1; FULL_CHECK_ID=""; return 75; }
  [ "$head_sha" = "$SHA" ] || { STATUS_SYNC_PENDING=1; FULL_CHECK_ID=""; return 75; }
  [ "$name" = "$CONTEXT_FULL" ] || { STATUS_SYNC_PENDING=1; FULL_CHECK_ID=""; return 75; }
  if [ "$state" = "success" ] || [ "$state" = "failure" ]; then
    [ "$conclusion" = "$state" ] || { STATUS_SYNC_PENDING=1; FULL_CHECK_ID=""; return 75; }
  fi
  FULL_CHECK_ID="$id"
  return 0
}

post_status() {
  local state="$1" context="$2" description="$3"
  [ "$POST_STATUS" -eq 1 ] || return 0
  if [ "$context" = "$CONTEXT_FULL" ]; then
    post_full_check "$state" "$description"
    return $?
  fi
  if ! gh api -X POST "repos/$REPO/statuses/$SHA" \
      -f state="$state" -f context="$context" -f description="${description:0:135}" >/dev/null 2>&1; then
    STATUS_SYNC_PENDING=1
    warn "não foi possível publicar status informativo '$context=$state'; evidência local preservada"
    return 75
  fi
  return 0
}

publish_success_statuses() {
  local c
  for c in "$CONTEXT_BACKEND" "$CONTEXT_EVAL" "$CONTEXT_FRONTEND" "$CONTEXT_P0" "$CONTEXT_GOV"; do
    post_status success "$c" "validado pelo fallback local isolado" || true
  done
  post_full_check success "todos os gates locais completos aprovados" || true
}

full_gate_is_green() {
  [ "$POST_STATUS" -eq 1 ] || return 1
  [[ "$FULL_CHECK_ID" =~ ^[1-9][0-9]*$ ]] || return 1
  local check
  check="$(ejc_github_app_gh_api "repos/$REPO/check-runs/$FULL_CHECK_ID" -H 'Accept: application/vnd.github+json' 2>/dev/null)" || return 1
  printf '%s' "$check" | jq -e \
    --arg name "$CONTEXT_FULL" --arg sha "$SHA" --argjson app_id "$FALLBACK_APP_ID" '
      .name == $name and
      .head_sha == $sha and
      .app.id == $app_id and
      .status == "completed" and
      .conclusion == "success"
    ' >/dev/null 2>&1
}

local_evidence_is_green() {
  python3 - "$SHA_EVIDENCE" "$SHA" <<'PY'
from __future__ import annotations
import hashlib
import json
import pathlib
import sys

base = pathlib.Path(sys.argv[1]).resolve()
target_sha = sys.argv[2]
pointer = base / "latest-success.json"
if not pointer.is_file():
    raise SystemExit(1)
try:
    latest = json.loads(pointer.read_text(encoding="utf-8"))
    rel = pathlib.PurePosixPath(latest["summary"])
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("summary path inseguro")
    summary_path = (base / pathlib.Path(*rel.parts)).resolve()
    attempts_root = (base / "attempts").resolve()
    if attempts_root not in summary_path.parents:
        raise ValueError("summary fora de attempts")
    raw = summary_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != latest["summary_sha256"]:
        raise ValueError("hash do summary divergente")
    summary = json.loads(raw)
    if summary.get("target_sha") != target_sha or summary.get("result") != "success":
        raise ValueError("summary não corresponde ao SHA/sucesso")
    for name, meta in (summary.get("logs") or {}).items():
        log_path = (summary_path.parent / name).resolve()
        if log_path.parent != summary_path.parent or not log_path.is_file():
            raise ValueError("log ausente/fora da tentativa")
        data = log_path.read_bytes()
        if len(data) != int(meta["bytes"]):
            raise ValueError("tamanho de log divergente")
        if hashlib.sha256(data).hexdigest() != meta["sha256"]:
            raise ValueError("hash de log divergente")
except Exception:
    raise SystemExit(1)
raise SystemExit(0)
PY
}

write_attempt_pointer() {
  python3 - "$SHA_EVIDENCE" "$ATTEMPT_DIR" "$SHA" <<'PY'
from __future__ import annotations
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

base = pathlib.Path(sys.argv[1]).resolve()
attempt = pathlib.Path(sys.argv[2]).resolve()
if base not in attempt.parents:
    raise SystemExit("attempt fora da raiz de evidência")
obj = {
    "schema": 1,
    "target_sha": sys.argv[3],
    "attempt": attempt.relative_to(base).as_posix(),
    "started_at": datetime.now(timezone.utc).isoformat(),
}
tmp = base / f".latest-attempt.{os.getpid()}.tmp"
tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
os.replace(tmp, base / "latest-attempt.json")
PY
}

write_attempt_summary() {
  local result="$1" failed_stage="${2:-}" exit_code="${3:-0}" promote_latest="${4:-0}"
  python3 - "$ATTEMPT_DIR" "$SHA_EVIDENCE" "$SHA" "$HEAD_REF" "$PR" "$result" "$failed_stage" "$exit_code" "$promote_latest" <<'PY'
from __future__ import annotations
import hashlib
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

attempt = pathlib.Path(sys.argv[1]).resolve()
base = pathlib.Path(sys.argv[2]).resolve()
obj = {
    "schema": 2,
    "target_sha": sys.argv[3],
    "ref": sys.argv[4],
    "pr": int(sys.argv[5]) if sys.argv[5] else None,
    "completed_at": datetime.now(timezone.utc).isoformat(),
    "result": sys.argv[6],
    "failed_stage": sys.argv[7] or None,
    "exit_code": int(sys.argv[8]),
    "logs": {},
}
for p in sorted(attempt.glob("*.log")):
    data = p.read_bytes()
    obj["logs"][p.name] = {
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }
raw = (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode()
summary = attempt / "summary.json"
tmp_summary = attempt / f".summary.{os.getpid()}.tmp"
tmp_summary.write_bytes(raw)
os.replace(tmp_summary, summary)

if sys.argv[9] == "1":
    rel = summary.relative_to(base).as_posix()
    latest = {
        "schema": 1,
        "target_sha": sys.argv[3],
        "summary": rel,
        "summary_sha256": hashlib.sha256(raw).hexdigest(),
        "promoted_at": datetime.now(timezone.utc).isoformat(),
    }
    tmp_latest = base / f".latest-success.{os.getpid()}.tmp"
    tmp_latest.write_text(json.dumps(latest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp_latest, base / "latest-success.json")
PY
}

revalidate_governance_for_merge() {
  [ -n "$PR" ] || return 1
  local gov_parent rc
  gov_parent="$WORKTREE_PARENT/merge-governance"
  mkdir -p "$gov_parent"
  GOV_WORKTREE="$gov_parent/${SHA:0:12}-$$"
  [ ! -e "$GOV_WORKTREE" ] || die "worktree temporário de governança já existe: $GOV_WORKTREE"
  git worktree add --detach "$GOV_WORKTREE" "$SHA" >/dev/null
  set +e
  (cd "$GOV_WORKTREE" && EJC_PR_NUMBER="$PR" EJC_GOV_REQUIRE_PR=1 \
    bash scripts/governanca/ci-local-governanca.sh) >/dev/null 2>&1
  rc=$?
  set -e
  git worktree remove --force "$GOV_WORKTREE" >/dev/null 2>&1 || true
  GOV_WORKTREE=""
  return "$rc"
}

refresh_status_from_evidence() {
  [ -n "$PR" ] || return 1
  if ! local_evidence_is_green; then
    log "Evidência local completa e íntegra do SHA exato ausente; status não promovido."
    return 1
  fi
  if ! revalidate_governance_for_merge; then
    post_status failure "$CONTEXT_GOV" "governança atual do PR reprovada" || true
    post_full_check failure "governança atual do PR reprovada" || true
    log "Governança atual do PR #$PR reprovada; status/merge retidos sem repetir a suíte pesada."
    return 1
  fi
  FULL_CHECK_ID=""
  publish_success_statuses
  if ! full_gate_is_green; then
    log "Check Run exato desta promoção não ficou verde; merge retido."
    return 1
  fi
  return 0
}

attempt_merge() {
  [ "$DO_MERGE" -eq 1 ] && [ -n "$PR" ] || return 0
  refresh_status_from_evidence || return 0

  local info labels files_json excecao
  info="$(gh pr view "$PR" --repo "$REPO" --json isDraft,mergeStateStatus,reviewDecision,labels,headRefOid)" \
    || { log "metadados do PR indisponíveis; merge retido"; return 0; }
  [ "$(printf '%s' "$info" | jq -r .headRefOid)" = "$SHA" ] || die "head do PR mudou após a validação"
  [ "$(printf '%s' "$info" | jq -r .isDraft)" = "false" ] || { log "PR #$PR em draft; não mesclado."; return 0; }
  labels="$(printf '%s' "$info" | jq -r '[.labels[].name] | join(",")')"
  case ",$labels," in *,retencao-humana,*) log "PR #$PR com retenção humana; não mesclado."; return 0;; esac

  if ! files_json="$(gh api --paginate "repos/$REPO/pulls/$PR/files?per_page=100" 2>/dev/null | jq -s 'add')"; then
    log "lista/diff de arquivos do PR indisponível; merge retido fail-closed"
    return 0
  fi
  printf '%s' "$files_json" | jq -e 'type == "array"' >/dev/null 2>&1 \
    || { log "resposta inválida ao listar arquivos do PR; merge retido"; return 0; }

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

ATTEMPT_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
ATTEMPT_DIR="$SHA_EVIDENCE/attempts/$ATTEMPT_ID"
mkdir -p "$ATTEMPT_DIR"
chmod 700 "$ATTEMPT_DIR" 2>/dev/null || true
write_attempt_pointer

WORKTREE="$WORKTREE_PARENT/${SHA:0:12}-$$"
git worktree add --detach "$WORKTREE" "$SHA" >/dev/null

for c in "$CONTEXT_BACKEND" "$CONTEXT_EVAL" "$CONTEXT_FRONTEND" "$CONTEXT_P0" "$CONTEXT_GOV"; do
  post_status pending "$c" "CI local isolado em execução" || true
done
post_full_check pending "CI local isolado em execução" || true

run_stage() {
  local key="$1" context="$2"; shift 2
  local logfile="$ATTEMPT_DIR/${key}.log"
  log "Executando $key…"
  set +e
  (cd "$WORKTREE" && "$@") >"$logfile" 2>&1
  local rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    write_attempt_summary failure "$key" "$rc" 0
    post_status failure "$context" "fallback local falhou: $key (exit $rc)" || true
    post_full_check failure "fallback local falhou: $key (exit $rc)" || true
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

# A prova local do código é criada somente depois de todos os gates pesados.
# O ponteiro latest-success é escrito atomicamente e referencia uma tentativa
# imutável; uma tentativa posterior que falhe não destrói a evidência anterior.
write_attempt_summary success "" 0 1

if [ -n "$PR" ] && ! revalidate_governance_for_merge; then
  post_status failure "$CONTEXT_GOV" "governança atual do PR reprovada" || true
  post_full_check failure "governança atual do PR reprovada" || true
  die "governança do PR mudou/reprovou após a suíte"
fi

publish_success_statuses
log "Fallback completo aprovado para $SHA. Evidência local: $SHA_EVIDENCE/latest-success.json"
[ "$STATUS_SYNC_PENDING" -eq 0 ] || warn "um ou mais sinais remotos não sincronizaram; watcher poderá republicar sem repetir a suíte"

attempt_merge
