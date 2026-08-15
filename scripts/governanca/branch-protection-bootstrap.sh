#!/usr/bin/env bash
# Recuperação administrativa fail-closed da proteção da main após #998/#1004.
# Em vez de substituir a branch protection completa com PUT, cria um ruleset
# aditivo. Rulesets agregam restrições, portanto uma restauração concorrente da
# proteção legada não é sobrescrita por este bootstrap.
set -euo pipefail
umask 077

CANONICAL_REPO="s2corporativo/ejc"
REPO="${EJC_REPO:-$CANONICAL_REPO}"
BRANCH="${EJC_BRANCH:-main}"
AUTH="${EJC_BRANCH_PROTECTION_BOOTSTRAP_AUTHORIZATION:-}"
RULESET_NAME="EJC main protection bootstrap #998"
GITHUB_ACTIONS_INTEGRATION_ID=15368

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
RULESETS_API="repos/$REPO/rulesets"

# Confirma que o alvo existe. Não exige protected=false: criar um ruleset é
# aditivo e seguro mesmo se outro administrador restaurar a proteção legada
# concorrentemente.
gh api "$BRANCH_API" -H 'Accept: application/vnd.github+json' >/dev/null \
  || fail "não foi possível ler a branch canônica"

payload="$(jq -cn --arg name "$RULESET_NAME" --argjson integration_id "$GITHUB_ACTIONS_INTEGRATION_ID" '{
  name: $name,
  target: "branch",
  enforcement: "active",
  bypass_actors: [],
  conditions: {
    ref_name: {
      include: ["refs/heads/main"],
      exclude: []
    }
  },
  rules: [
    {type:"deletion"},
    {type:"non_fast_forward"},
    {type:"required_linear_history"},
    {
      type:"pull_request",
      parameters:{
        allowed_merge_methods:["merge","squash","rebase"],
        dismiss_stale_reviews_on_push:true,
        require_code_owner_review:true,
        require_last_push_approval:true,
        required_approving_review_count:1,
        required_review_thread_resolution:true
      }
    },
    {
      type:"required_status_checks",
      parameters:{
        do_not_enforce_on_create:false,
        required_status_checks:[
          {context:"Backend — suíte completa + schema/RAG (Postgres pgvector)", integration_id:$integration_id},
          {context:"Eval — smoke dos gold sets (offline, bloqueante)", integration_id:$integration_id},
          {context:"Frontend — testes + typecheck + build", integration_id:$integration_id},
          {context:"P0 guard — conflitos e segredos", integration_id:$integration_id},
          {context:"Governança — travas de PR", integration_id:$integration_id}
        ],
        strict_required_status_checks_policy:true
      }
    }
  ]
}')"

ruleset_matches_payload() {
  local current="$1"
  printf '%s' "$current" | jq -e --arg name "$RULESET_NAME" --argjson integration_id "$GITHUB_ACTIONS_INTEGRATION_ID" '
    (.name == $name) and
    (.target == "branch") and
    (.enforcement == "active") and
    ((.bypass_actors | type) == "array") and
    ((.bypass_actors | length) == 0) and
    (.conditions.ref_name.include == ["refs/heads/main"]) and
    (.conditions.ref_name.exclude == []) and
    ([.rules[].type] | sort == (["deletion","non_fast_forward","pull_request","required_linear_history","required_status_checks"] | sort)) and
    ((.rules[] | select(.type == "pull_request") | .parameters) as $pr |
      ($pr.dismiss_stale_reviews_on_push == true) and
      ($pr.require_code_owner_review == true) and
      ($pr.require_last_push_approval == true) and
      ($pr.required_approving_review_count >= 1) and
      ($pr.required_review_thread_resolution == true)) and
    ((.rules[] | select(.type == "required_status_checks") | .parameters) as $sc |
      ($sc.do_not_enforce_on_create == false) and
      ($sc.strict_required_status_checks_policy == true) and
      (($sc.required_status_checks | sort_by(.context,.integration_id)) == ([
        {context:"Backend — suíte completa + schema/RAG (Postgres pgvector)", integration_id:$integration_id},
        {context:"Eval — smoke dos gold sets (offline, bloqueante)", integration_id:$integration_id},
        {context:"Frontend — testes + typecheck + build", integration_id:$integration_id},
        {context:"P0 guard — conflitos e segredos", integration_id:$integration_id},
        {context:"Governança — travas de PR", integration_id:$integration_id}
      ] | sort_by(.context,.integration_id))))
  ' >/dev/null
}

find_ruleset_ids() {
  gh api "$RULESETS_API?includes_parents=false&targets=branch&per_page=100" \
    -H 'Accept: application/vnd.github+json' \
    | jq -r --arg name "$RULESET_NAME" '.[] | select(.name == $name) | .id'
}

reconcile_ruleset() {
  local ids count id current
  ids="$(find_ruleset_ids)" || fail "não foi possível listar rulesets para reconciliação"
  count="$(printf '%s\n' "$ids" | sed '/^$/d' | wc -l | tr -d ' ')"
  [ "$count" -eq 1 ] || fail "esperado exatamente um ruleset canônico após bootstrap; encontrados $count"
  id="$(printf '%s\n' "$ids" | sed '/^$/d')"
  current="$(gh api "$RULESETS_API/$id" -H 'Accept: application/vnd.github+json')" \
    || fail "não foi possível ler ruleset canônico após bootstrap"
  ruleset_matches_payload "$current" \
    || fail "ruleset efetivo diverge do baseline fail-closed"
}

existing_ids="$(find_ruleset_ids)" || fail "não foi possível listar rulesets existentes"
existing_count="$(printf '%s\n' "$existing_ids" | sed '/^$/d' | wc -l | tr -d ' ')"
if [ "$existing_count" -gt 1 ]; then
  fail "mais de um ruleset com nome canônico; intervenção administrativa necessária"
fi
if [ "$existing_count" -eq 1 ]; then
  existing_id="$(printf '%s\n' "$existing_ids" | sed '/^$/d')"
  existing_json="$(gh api "$RULESETS_API/$existing_id" -H 'Accept: application/vnd.github+json')" \
    || fail "não foi possível ler ruleset canônico existente"
  ruleset_matches_payload "$existing_json" \
    || fail "ruleset canônico já existe, mas diverge do baseline; recuso sobrescrever"
  ok "ruleset canônico já estava ativo e íntegro"
  exit 0
fi

# POST cria uma política nova e aditiva. Não há PUT/PATCH/DELETE neste bootstrap,
# portanto uma proteção legada restaurada concorrentemente não é substituída.
if ! printf '%s' "$payload" | gh api -X POST "$RULESETS_API" \
    -H 'Accept: application/vnd.github+json' --input - >/dev/null; then
  aviso "POST não retornou resposta confiável; reconciliando estado efetivo"
fi

reconcile_ruleset
ok "ruleset fail-closed da main criado e confirmado sem sobrescrever proteção concorrente"
