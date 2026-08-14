#!/usr/bin/env bash
# Recuperação administrativa da proteção COMPLETA da main quando a branch está
# comprovadamente sem proteção. Não é usada pelo fallback normal e recusa
# sobrescrever uma proteção já existente.
set -euo pipefail
umask 077

REPO="${EJC_REPO:-s2corporativo/ejc}"
BRANCH="${EJC_BRANCH:-main}"
AUTH="${EJC_BRANCH_PROTECTION_BOOTSTRAP_AUTHORIZATION:-}"

fail() { printf 'ABORTADO: %s\n' "$1" >&2; exit 1; }
ok() { printf '[ok] %s\n' "$1"; }

command -v gh >/dev/null 2>&1 || fail "GitHub CLI (gh) ausente"
command -v jq >/dev/null 2>&1 || fail "jq ausente"
gh auth status >/dev/null 2>&1 || fail "gh não autenticado"
[ "$AUTH" = "998" ] || fail "exige EJC_BRANCH_PROTECTION_BOOTSTRAP_AUTHORIZATION=998"
[ "$BRANCH" = "main" ] || fail "bootstrap autorizado somente para main"

BRANCH_API="repos/$REPO/branches/$BRANCH"
PROTECTION_API="repos/$REPO/branches/$BRANCH/protection"

branch_json="$(gh api "$BRANCH_API" -H 'Accept: application/vnd.github+json')" \
  || fail "não foi possível ler a branch"
protected="$(printf '%s' "$branch_json" | jq -r '.protected // false')"
[ "$protected" = "false" ] \
  || fail "branch já possui proteção; recuso sobrescrever política existente"

payload="$(jq -cn '{
  required_status_checks: {
    strict: true,
    contexts: [
      "Backend — suíte completa + schema/RAG (Postgres pgvector)",
      "Eval — smoke dos gold sets (offline, bloqueante)",
      "Frontend — testes + typecheck + build",
      "P0 guard — conflitos e segredos",
      "Governança — travas de PR"
    ]
  },
  enforce_admins: true,
  required_pull_request_reviews: {
    dismiss_stale_reviews: true,
    require_code_owner_reviews: true,
    required_approving_review_count: 1,
    require_last_push_approval: true
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

# PUT é deliberadamente usado somente neste bootstrap: a branch foi comprovada
# desprotegida. O fluxo normal continua alterando apenas required_status_checks.
printf '%s' "$payload" | gh api -X PUT "$PROTECTION_API" \
  -H 'Accept: application/vnd.github+json' --input - >/dev/null \
  || fail "falha ao aplicar proteção completa"

current="$(gh api "$PROTECTION_API" -H 'Accept: application/vnd.github+json')" \
  || fail "proteção aplicada, mas read-after-write falhou"

printf '%s' "$current" | jq -e '
  (.required_status_checks.strict == true) and
  ((.required_status_checks.contexts // []) | sort == ([
    "Backend — suíte completa + schema/RAG (Postgres pgvector)",
    "Eval — smoke dos gold sets (offline, bloqueante)",
    "Frontend — testes + typecheck + build",
    "P0 guard — conflitos e segredos",
    "Governança — travas de PR"
  ] | sort)) and
  (.enforce_admins.enabled == true) and
  (.required_pull_request_reviews.dismiss_stale_reviews == true) and
  (.required_pull_request_reviews.require_code_owner_reviews == true) and
  (.required_pull_request_reviews.required_approving_review_count >= 1) and
  (.required_pull_request_reviews.require_last_push_approval == true) and
  (.required_linear_history.enabled == true) and
  (.allow_force_pushes.enabled == false) and
  (.allow_deletions.enabled == false) and
  (.required_conversation_resolution.enabled == true)
' >/dev/null || fail "estado efetivo não corresponde ao baseline fail-closed"

ok "proteção completa da main restaurada e confirmada por read-after-write"
