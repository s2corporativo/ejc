#!/usr/bin/env bash
# =============================================================================
# branch-protection.sh — proteção da main do EJC.
#
# Modos:
#   --contextos          lista checks reportados no HEAD
#   --verificar          lê a configuração vigente
#   --dry-run            mostra política cloud (GitHub Actions)
#   --dry-run-fallback   mostra política fallback local
#   --cloud              aplica contexts do CI em nuvem
#   --fallback           aplica EJC Local Full Gate (CI externo/local)
#
# Requisitos: gh autenticado com permissão de admin no repositório.
# A alteração é reversível e salva backup em var/ (gitignored).
# =============================================================================
set -euo pipefail

REPO="${EJC_REPO:-s2corporativo/ejc}"
BRANCH="${EJC_BRANCH:-main}"
MODO="${1:---cloud}"

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

# Em contingência, strict/reviews/CODEOWNERS/conversas permanecem. Só o contexto
# obrigatório muda. Mantemos o MESMO mecanismo `contexts` já usado pela proteção
# atual do EJC, agora apontado para o commit status clássico que o fallback local
# publica após a suíte integral.
read -r -d '' PAYLOAD_FALLBACK <<'JSON' || true
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "EJC Local Full Gate"
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

if [ "$MODO" = "--contextos" ]; then
  SHA="$(gh api "repos/$REPO/commits/$BRANCH" --jq .sha 2>/dev/null)" \
    || falhar "nao foi possivel ler o HEAD de $BRANCH."
  echo "Checks efetivamente reportados no HEAD de $BRANCH:"
  gh api "repos/$REPO/commits/$SHA/check-runs?per_page=100" --jq '.check_runs[].name' 2>/dev/null | sort -u || true
  echo "Commit statuses:"
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
  --dry-run-fallback) PAYLOAD="$PAYLOAD_FALLBACK"; LABEL="fallback local" ;;
  --cloud) PAYLOAD="$PAYLOAD_CLOUD"; LABEL="cloud" ;;
  --fallback) PAYLOAD="$PAYLOAD_FALLBACK"; LABEL="fallback local" ;;
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
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="var/branch-protection-anterior-$STAMP.json"
if gh api "repos/$REPO/branches/$BRANCH/protection" > "$BACKUP" 2>/dev/null; then
  cp "$BACKUP" var/branch-protection-anterior.json
  ok "salvo em $BACKUP"
else
  echo "null" > "$BACKUP"; cp "$BACKUP" var/branch-protection-anterior.json
  ok "branch sem protecao anterior (backup null)"
fi

echo ""
echo "2. Aplicando protecao: $LABEL"
echo "$PAYLOAD" | gh api -X PUT "repos/$REPO/branches/$BRANCH/protection" --input - >/dev/null \
  || falhar "falha ao aplicar proteção"
ok "protecao aplicada"

echo ""
echo "3. Verificacao"
gh api "repos/$REPO/branches/$BRANCH/protection" \
  --jq '{
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

cat <<'FIM'

Leitura esperada em ambos os modos:
- enforce_admins, strict, CODEOWNERS, review, conversa resolvida e histórico linear permanecem ativos;
- force push e deleção continuam proibidos.

Modo --cloud: cinco contexts canônicos do Actions.
Modo --fallback: somente o context `EJC Local Full Gate`, produzido pelo fallback
local completo após validação real do SHA em worktree isolado.
FIM
