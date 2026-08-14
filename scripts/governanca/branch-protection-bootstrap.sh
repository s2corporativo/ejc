#!/usr/bin/env bash
# Recuperação administrativa da proteção COMPLETA da main quando a branch está
# comprovadamente sem proteção. Não é usada pelo fallback normal e recusa
# sobrescrever uma proteção já existente.
set -euo pipefail
umask 077

CANONICAL_REPO="s2corporativo/ejc"
REPO="${EJC_REPO:-$CANONICAL_REPO}"
BRANCH="${EJC_BRANCH:-main}"
AUTH="${EJC_BRANCH_PROTECTION_BOOTSTRAP_AUTHORIZATION:-}"
GITHUB_ACTIONS_APP_ID=15368

fail() { printf 'ABORTADO: %s\n' "$1" >&2; exit 1; }
ok() { printf '[ok] %s\n' "$1"; }
aviso() { printf '[aviso] %s\n' "$1" >&2; }

command -v gh >/dev/null 2>&1 || fail "GitHub CLI (gh) ausente"
command -v jq >/dev/null 2>&1 || fail "jq ausente"
gh auth status >/dev/null 2>&1 || fail "gh não autenticado"
[ "$AUTH" = "998" ] || fail "exige EJC_BRANCH_PROTECTION_BOOTSTRAP_AUTHORIZATION=998"
[ "$REPO" = "$CANONICAL_REPO" ] || fail "bootstrap autorizado somente para $CANONICAL_REPO"
[ "$BRANCH" = "main" ] || fail "bootstrap autorizado somente para main"

BRANCH_API="repos/$REPO/branches/$BRANCH"
PROTECTION_API="repos/$REPO/branches/$BRANCH/protection"

assert_branch_unprotected() {
  local branch_json
  branch_json="$(gh api "$BRANCH_API" -H 'Accept: application/vnd.github+json')" \
    || fail "não foi possível ler a branch"
  printf '%s' "$branch_json" | jq -e '
    has("protected") and
    (.protected | type == "boolean") and
    (.protected == false)
  ' >/dev/null || fail "estado de proteção ausente, ambíguo ou já protegido; recuso sobrescrever política existente"
}

payload="$(jq -cn --argjson app_id "$GITHUB_ACTIONS_APP_ID" '{
  required_status_checks: {
    strict: true,
    checks: [
      {context:"Backend — suíte completa + schema/RAG (Postgres pgvector)", app_id:$app_id},
      {context:"Eval — smoke dos gold sets (offline, bloqueante)", app_id:$app_id},
      {context:"Frontend — testes + typecheck + build", app_id:$app_id},
      {context:"P0 guard — conflitos e segredos", app_id:$app_id},
      {context:"Governança — travas de PR", app_id:$app_id}
    ]
  },
  enforce_admins: true,
  required_pull_request_reviews: {
    dismiss_stale_reviews: true,
    require_code_owner_reviews: true,
    required_approving_review_count: 1,
    require_last_push_approval: true,
    bypass_pull_request_allowances: {users:[], teams:[], apps:[]}
  },
  restrictions: null,
  required_linear_history: true,
  allow_force_pushes: false,
  allow_deletions: false,
  block_creations: false,
  required_conversation_resolution: true,
  lock_branch: false,
  allow_fork_syncing: false
}')"

protection_matches_payload() {
  local current="$1"
  printf '%s' "$current" | jq -e --argjson app_id "$GITHUB_ACTIONS_APP_ID" '
    (.required_status_checks.strict == true) and
    ((.required_status_checks.checks // []) | sort_by(.context, .app_id) == ([
      {context:"Backend — suíte completa + schema/RAG (Postgres pgvector)", app_id:$app_id},
      {context:"Eval — smoke dos gold sets (offline, bloqueante)", app_id:$app_id},
      {context:"Frontend — testes + typecheck + build", app_id:$app_id},
      {context:"P0 guard — conflitos e segredos", app_id:$app_id},
      {context:"Governança — travas de PR", app_id:$app_id}
    ] | sort_by(.context, .app_id))) and
    (.enforce_admins.enabled == true) and
    (.required_pull_request_reviews.dismiss_stale_reviews == true) and
    (.required_pull_request_reviews.require_code_owner_reviews == true) and
    (.required_pull_request_reviews.required_approving_review_count >= 1) and
    (.required_pull_request_reviews.require_last_push_approval == true) and
    ((.required_pull_request_reviews.bypass_pull_request_allowances | type) == "object") and
    (.required_pull_request_reviews.bypass_pull_request_allowances | has("users") and has("teams") and has("apps")) and
    ((.required_pull_request_reviews.bypass_pull_request_allowances.users | type) == "array") and
    ((.required_pull_request_reviews.bypass_pull_request_allowances.teams | type) == "array") and
    ((.required_pull_request_reviews.bypass_pull_request_allowances.apps | type) == "array") and
    ((.required_pull_request_reviews.bypass_pull_request_allowances.users | length) == 0) and
    ((.required_pull_request_reviews.bypass_pull_request_allowances.teams | length) == 0) and
    ((.required_pull_request_reviews.bypass_pull_request_allowances.apps | length) == 0) and
    (.restrictions == null) and
    (.required_linear_history.enabled == true) and
    (.allow_force_pushes.enabled == false) and
    (.allow_deletions.enabled == false) and
    (.block_creations.enabled == false) and
    (.required_conversation_resolution.enabled == true) and
    (.lock_branch.enabled == false) and
    (.allow_fork_syncing.enabled == false)
  ' >/dev/null
}

reconcile_protection() {
  local current
  current="$(gh api "$PROTECTION_API" -H 'Accept: application/vnd.github+json')" \
    || fail "não foi possível reconciliar a proteção após a tentativa de PUT"
  protection_matches_payload "$current" \
    || fail "estado efetivo não corresponde ao baseline fail-closed"
}

# Dupla leitura fail-closed: a segunda ocorre imediatamente antes da mutação e
# reduz a janela TOCTOU. Se outra restauração já estiver visível, o PUT não roda.
assert_branch_unprotected
assert_branch_unprotected

# PUT é deliberadamente usado somente neste bootstrap. Mesmo se a conexão cair
# depois de o GitHub aplicar a política, a decisão final vem do GET de
# reconciliação, nunca do status de transporte isoladamente.
if ! printf '%s' "$payload" | gh api -X PUT "$PROTECTION_API" \
    -H 'Accept: application/vnd.github+json' --input - >/dev/null; then
  aviso "PUT não retornou resposta confiável; reconciliando estado efetivo"
fi

reconcile_protection
ok "proteção completa da main restaurada e confirmada por read-after-write"
