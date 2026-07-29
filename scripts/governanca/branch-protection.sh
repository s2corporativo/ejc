#!/usr/bin/env bash
# =============================================================================
#  branch-protection.sh
#  Configura a protecao da branch main no repositorio s2corporativo/ejc.
#  Sem isto, a governanca e apenas declaratoria: nada impede push direto ou merge.
#
#  Uso:
#    bash scripts/governanca/branch-protection.sh --contextos  # lista checks reais reportados
#    bash scripts/governanca/branch-protection.sh --dry-run    # mostra o payload, nao aplica
#    bash scripts/governanca/branch-protection.sh              # aplica
#    bash scripts/governanca/branch-protection.sh --verificar  # le a configuracao vigente
#
#  Requisitos: gh autenticado com permissao de admin no repositorio.
#  Reversivel: a configuracao anterior e salva em ./branch-protection-anterior.json
#
#  ATO ADMINISTRATIVO HUMANO. Nenhum agente executa este script sem autorizacao
#  expressa do titular (CLAUDE.md, regras 8 e 9).
# =============================================================================
set -euo pipefail

REPO="${EJC_REPO:-s2corporativo/ejc}"
BRANCH="${EJC_BRANCH:-main}"
MODO="${1:-aplicar}"

falhar() { echo ""; echo "ABORTADO: $1"; exit 1; }
ok() { echo "  [ok] $1"; }

command -v gh >/dev/null 2>&1 || falhar "GitHub CLI (gh) nao encontrado."
gh auth status >/dev/null 2>&1 || falhar "gh nao autenticado. Execute: gh auth login"

echo "Repositorio: $REPO   Branch: $BRANCH"
echo ""

# ---------------------------------------------------------------------------
# Contextos de status check exigidos.
#
# ATENCAO: o contexto e o campo `name:` do job, nao o id do job. Os valores
# abaixo foram extraidos de .github/workflows/ em 2026-07-29:
#
#   ci.yml                 -> db-validation   : "Backend — suíte completa + schema/RAG (Postgres pgvector)"
#                             eval-smoke      : "Eval — smoke dos gold sets (offline, bloqueante)"
#                             frontend-build  : "Frontend — testes + typecheck + build"
#   ejc-release-gate.yml   -> p0-guard        : "P0 guard — conflitos e segredos"
#   governanca.yml         -> governanca      : "Governança — travas de PR"
#
# Se um contexto exigido nunca for reportado, NENHUM PR sera mesclavel.
# Rode `--contextos` antes de aplicar e confira os nomes contra a saida real.
# Renomear um job em .github/workflows/ obriga a reaplicar este script.
# ---------------------------------------------------------------------------
read -r -d '' PAYLOAD <<'JSON' || true
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "Backend — suíte completa + schema/RAG (Postgres pgvector)",
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

if [ "$MODO" = "--contextos" ]; then
  echo "Checks efetivamente reportados no HEAD de $BRANCH:"
  SHA="$(gh api "repos/$REPO/commits/$BRANCH" --jq .sha 2>/dev/null)" \
    || falhar "nao foi possivel ler o HEAD de $BRANCH."
  gh api "repos/$REPO/commits/$SHA/check-runs" --jq '.check_runs[].name' 2>/dev/null | sort -u \
    || echo "  (nenhum check run registrado neste commit)"
  echo ""
  echo "Compare com a lista de contextos no topo deste script. Divergencia de"
  echo "uma unica letra ou acento torna a branch immergivel."
  exit 0
fi

if [ "$MODO" = "--verificar" ]; then
  echo "Configuracao vigente:"
  gh api "repos/$REPO/branches/$BRANCH/protection" 2>/dev/null \
    || echo "  (branch sem protecao configurada)"
  exit 0
fi

if [ "$MODO" = "--dry-run" ]; then
  echo "Payload que seria aplicado (PUT repos/$REPO/branches/$BRANCH/protection):"
  echo "$PAYLOAD"
  echo ""
  echo "Nada foi alterado."
  exit 0
fi

echo "1. Backup da configuracao atual"
if gh api "repos/$REPO/branches/$BRANCH/protection" > branch-protection-anterior.json 2>/dev/null; then
  ok "salvo em branch-protection-anterior.json"
else
  echo "null" > branch-protection-anterior.json
  ok "branch nao possuia protecao (backup registrado como null)"
fi

echo ""
echo "2. Aplicando protecao"
echo "$PAYLOAD" | gh api -X PUT "repos/$REPO/branches/$BRANCH/protection" --input - >/dev/null \
  || falhar "falha ao aplicar. Verifique permissao de admin e se os contextos de status check existem."
ok "protecao aplicada"

echo ""
echo "3. Verificacao"
gh api "repos/$REPO/branches/$BRANCH/protection" \
  --jq '{
    push_direto_bloqueado: .enforce_admins.enabled,
    aprovacoes_exigidas: .required_pull_request_reviews.required_approving_review_count,
    codeowners_obrigatorio: .required_pull_request_reviews.require_code_owner_reviews.enabled,
    dispensa_review_ao_novo_push: .required_pull_request_reviews.dismiss_stale_reviews.enabled,
    branch_atualizada_exigida: .required_status_checks.strict,
    checks_exigidos: .required_status_checks.contexts,
    force_push: .allow_force_pushes.enabled,
    delecao: .allow_deletions.enabled,
    historico_linear: .required_linear_history.enabled,
    conversas_resolvidas: .required_conversation_resolution.enabled
  }'

cat <<'FIM'

============================================================
 Leitura esperada
============================================================
  push_direto_bloqueado ......... true
  aprovacoes_exigidas ........... 1
  codeowners_obrigatorio ........ true
  branch_atualizada_exigida ..... true
  force_push .................... false
  delecao ....................... false

Se checks_exigidos contiver nome de job inexistente, nenhum PR sera
mesclavel. Rode `--contextos`, corrija a lista no topo deste script e
reaplique.

Reverter:  gh api -X DELETE repos/<repo>/branches/main/protection
FIM
