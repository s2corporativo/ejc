#!/usr/bin/env bash
# =============================================================================
# branch-protection.sh — proteção da main do EJC.
#
# Modos:
#   --contextos          lista checks reportados no HEAD
#   --verificar          lê a configuração vigente (DEFAULT seguro)
#   --dry-run            mostra política cloud (GitHub Actions)
#   --dry-run-fallback   mostra política fallback local
#   --cloud              aplica contexts do CI em nuvem
#   --fallback           aplica EJC Local Full Gate (CI externo/local)
#
# Requisitos: gh autenticado com permissão de admin no repositório.
# A alteração é reversível e salva backup em var/ (gitignored).
#
# ATO ADMINISTRATIVO PROTEGIDO: o modo --fallback só pode ser aplicado conforme
# decisão expressa e registrada do titular. A autorização vigente está na Issue
# #998; o ativador canônico injeta EJC_FALLBACK_AUTHORIZATION=998. Esta trava
# não serve para contornar checks: ela apenas troca o executor obrigatório,
# preservando strict, reviews, CODEOWNERS e todas as demais proteções.
#
# SEGURANÇA: o gate fallback é um Check Run vinculado a um GitHub App dedicado.
# `contexts`/commit status clássico (app_id=-1) nunca é aceito no modo fallback.
# =============================================================================
set -euo pipefail

REPO="${EJC_REPO:-s2corporativo/ejc}"
BRANCH="${EJC_BRANCH:-main}"
MODO="${1:---verificar}"
FALLBACK_AUTHORIZATION="${EJC_FALLBACK_AUTHORIZATION:-}"
FALLBACK_APP_ID="${EJC_FALLBACK_APP_ID:-}"

falhar() { echo ""; echo "ABORTADO: $1"; exit 1; }
ok() { echo "  [ok] $1"; }

command -v gh >/dev/null 2>&1 || falhar "GitHub CLI (gh) nao encontrado."
gh auth status >/dev/null 2>&1 || falhar "gh nao autenticado."

echo "Repositorio: $REPO   Branch: $BRANCH"
echo ""

read -r -d '' PAYLOAD_CLOUD <<'JSON' || true
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "Backend — suíte completa + schema/RAG (Postgres pgvector)",
      "Eval — smoke dos gold sets (offline, bloqueante)",
      "Frontend — testes + typecheck + build",
      "P0 guard — conflitos e segredos",
      "Governança — travas de PR"
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": true,
    "require_last_push_approval": true
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": true,
  "required_linear_history": true,
  "lock_branch": false,
  "allow_fork_syncing": false
}
JSON

build_fallback_payload() {
  [[ "$FALLBACK_APP_ID" =~ ^[1-9][0-9]*$ ]] \
    || falhar "modo fallback exige EJC_FALLBACK_APP_ID numérico (>0) do GitHub App dedicado"
  jq -cn --argjson app_id "$FALLBACK_APP_ID" '{
    required_status_checks: {
      strict: true,
      checks: [
        {context: "EJC Local Full Gate", app_id: $app_id}
      ]
    },
    enforce_admins: true,
    required_pull_request_reviews: {
      required_approving_review_count: 1,
      dismiss_stale_reviews: true,
      require_code_owner_reviews: true,
      require_last_push_approval: true
    },
    restrictions: null,
    allow_force_pushes: false,
    allow_deletions: false,
    block_creations: false,
    required_conversation_resolution: true,
    required_linear_history: true,
    lock_branch: false,
    allow_fork_syncing: false
  }'
}

if [ "$MODO" = "--contextos" ]; then
  SHA="$(gh api "repos/$REPO/commits/$BRANCH" --jq .sha 2>/dev/null)" \
    || falhar "nao foi possivel ler o HEAD de $BRANCH."
  echo "Checks efetivamente reportados no HEAD de $BRANCH:"
  gh api "repos/$REPO/commits/$SHA/check-runs?per_page=100" --jq '.check_runs[] | [.name, (.app.id|tostring), .conclusion] | @tsv' 2>/dev/null | sort -u || true
  echo "Commit statuses (informativos; nunca satisfazem o gate fallback):"
  gh api "repos/$REPO/commits/$SHA/status" --jq '.statuses[].context' 2>/dev/null | sort -u || true
  exit 0
fi

if [ "$MODO" = "--verificar" ]; then
  gh api "repos/$REPO/branches/$BRANCH/protection" 2>/dev/null \
    || echo "  (branch sem protecao configurada)"
  exit 0
fi

case "$MODO" in
  --dry-run) PAYLOAD="$PAYLOAD_CLOUD"; LABEL="cloud" ;;
  --dry-run-fallback) PAYLOAD="$(build_fallback_payload)"; LABEL="fallback local" ;;
  --cloud) PAYLOAD="$PAYLOAD_CLOUD"; LABEL="cloud" ;;
  --fallback)
    [ "$FALLBACK_AUTHORIZATION" = "998" ] \
      || falhar "modo --fallback exige EJC_FALLBACK_AUTHORIZATION=998 (decisão registrada na Issue #998)"
    PAYLOAD="$(build_fallback_payload)"; LABEL="fallback local" ;;
  *) falhar "modo inválido: $MODO" ;;
esac

if [ "$MODO" = "--dry-run" ] || [ "$MODO" = "--dry-run-fallback" ]; then
  echo "Politica $LABEL que seria aplicada:"
  echo "$PAYLOAD"
  echo "Nada foi alterado."
  exit 0
fi

echo "1. Backup da configuracao atual"
mkdir -p var
STAMP="$(date -u +%Y%m%dT%H%M%SZ)-$$"
BACKUP="var/branch-protection-anterior-$STAMP.json"
BACKUP_ERR="$(mktemp)"
cleanup_backup_err() { rm -f "$BACKUP_ERR"; }
trap cleanup_backup_err EXIT
if gh api "repos/$REPO/branches/$BRANCH/protection" > "$BACKUP" 2>"$BACKUP_ERR"; then
  cp "$BACKUP" var/branch-protection-anterior.json
  ok "salvo em $BACKUP"
elif grep -Eq '(^|[^0-9])404([^0-9]|$)|HTTP 404|Not Found' "$BACKUP_ERR"; then
  echo "null" > "$BACKUP"
  cp "$BACKUP" var/branch-protection-anterior.json
  ok "branch sem protecao anterior (backup null)"
else
  cat "$BACKUP_ERR" >&2 || true
  rm -f "$BACKUP"
  falhar "nao foi possivel ler a protecao atual de $BRANCH; backup estável preservado e nada foi alterado"
fi
rm -f "$BACKUP_ERR"
trap - EXIT

echo ""
echo "2. Aplicando protecao: $LABEL"
echo "$PAYLOAD" | gh api -X PUT "repos/$REPO/branches/$BRANCH/protection" --input - >/dev/null \
  || falhar "falha ao aplicar proteção"
ok "protecao aplicada"

echo ""
echo "3. Verificacao"
PROTECTION_JSON="$(gh api "repos/$REPO/branches/$BRANCH/protection")"
printf '%s' "$PROTECTION_JSON" | jq '{
  push_direto_bloqueado: .enforce_admins.enabled,
  aprovacoes_exigidas: .required_pull_request_reviews.required_approving_review_count,
  codeowners_obrigatorio: .required_pull_request_reviews.require_code_owner_reviews.enabled,
  branch_atualizada_exigida: .required_status_checks.strict,
  contexts: (.required_status_checks.contexts // []),
  checks: (.required_status_checks.checks // []),
  force_push: .allow_force_pushes.enabled,
  delecao: .allow_deletions.enabled,
  historico_linear: .required_linear_history.enabled,
  conversas_resolvidas: .required_conversation_resolution.enabled
}'

if [ "$MODO" = "--fallback" ]; then
  printf '%s' "$PROTECTION_JSON" | jq -e --argjson app_id "$FALLBACK_APP_ID" '
    (.required_status_checks.contexts // []) == [] and
    ((.required_status_checks.checks // []) | length) == 1 and
    (.required_status_checks.checks[0].context == "EJC Local Full Gate") and
    (.required_status_checks.checks[0].app_id == $app_id)
  ' >/dev/null || falhar "proteção fallback aplicada sem vínculo exclusivo ao GitHub App esperado"
  ok "EJC Local Full Gate vinculado ao GitHub App id=$FALLBACK_APP_ID"
fi

cat <<'FIM'

Leitura esperada em ambos os modos:
- enforce_admins, strict, CODEOWNERS, review, conversa resolvida e histórico linear permanecem ativos;
- force push e deleção continuam proibidos.

Modo --cloud: cinco contexts canônicos do Actions.
Modo --fallback: somente o check `EJC Local Full Gate`, vinculado por `app_id`
ao GitHub App dedicado. Commit status clássico/app_id=-1 não satisfaz esse gate.
A aplicação desse modo exige autorização registrada da Issue #998.

Sem argumento, este script executa somente `--verificar` e não altera a proteção.
FIM
