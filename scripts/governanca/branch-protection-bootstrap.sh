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
LOCK_REF="refs/tags/ejc-bootstrap-ruleset-lock-998"
LOCK_REF_ENDPOINT="repos/$REPO/git/ref/tags/ejc-bootstrap-ruleset-lock-998"
LOCK_REFS_ENDPOINT="repos/$REPO/git/refs"
LOCK_WAIT_ATTEMPTS="${EJC_BOOTSTRAP_LOCK_WAIT_ATTEMPTS:-15}"
LOCK_WAIT_SECONDS="${EJC_BOOTSTRAP_LOCK_WAIT_SECONDS:-2}"

fail() { printf 'ABORTADO: %s\n' "$1" >&2; exit 1; }
ok() { printf '[ok] %s\n' "$1"; }
aviso() { printf '[aviso] %s\n' "$1" >&2; }

command -v gh >/dev/null 2>&1 || fail "GitHub CLI (gh) ausente"
command -v jq >/dev/null 2>&1 || fail "jq ausente"
gh auth status >/dev/null 2>&1 || fail "gh não autenticado"
[ "$AUTH" = "998" ] || fail "exige EJC_BRANCH_PROTECTION_BOOTSTRAP_AUTHORIZATION=998"
[ "$REPO" = "$CANONICAL_REPO" ] || fail "bootstrap autorizado somente para $CANONICAL_REPO"
[ "$BRANCH" = "main" ] || fail "bootstrap autorizado somente para main"
[[ "$LOCK_WAIT_ATTEMPTS" =~ ^[1-9][0-9]*$ ]] || fail "EJC_BOOTSTRAP_LOCK_WAIT_ATTEMPTS inválido"

BRANCH_API="repos/$REPO/branches/$BRANCH"
RULESETS_API="repos/$REPO/rulesets"

branch_json="$(gh api "$BRANCH_API" -H 'Accept: application/vnd.github+json')" \
  || fail "não foi possível ler a branch canônica"
lock_sha="$(printf '%s' "$branch_json" | jq -r '.commit.sha // empty')"
[[ "$lock_sha" =~ ^[0-9a-fA-F]{40}$ ]] \
  || fail "resposta da API da main não contém SHA válido para o lock remoto"

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
        allowed_merge_methods:["squash","rebase"],
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
          {context:"Governança — travas de PR", integration_id:$integration_id},
          {context:"Bootstrap protection — security auditor", integration_id:$integration_id}
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
      (($pr.allowed_merge_methods | sort) == (["rebase","squash"] | sort)) and
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
        {context:"Governança — travas de PR", integration_id:$integration_id},
        {context:"Bootstrap protection — security auditor", integration_id:$integration_id}
      ] | sort_by(.context,.integration_id))))
  ' >/dev/null
}

find_ruleset_ids() {
  gh api "$RULESETS_API?includes_parents=false&targets=branch&per_page=100" \
    -H 'Accept: application/vnd.github+json' \
    | jq -r --arg name "$RULESET_NAME" '.[] | select(.name == $name) | .id'
}

count_ruleset_ids() {
  printf '%s\n' "$1" | sed '/^$/d' | wc -l | tr -d ' '
}

validate_single_ruleset() {
  local ids="$1" id current
  id="$(printf '%s\n' "$ids" | sed '/^$/d')"
  current="$(gh api "$RULESETS_API/$id" -H 'Accept: application/vnd.github+json')" \
    || fail "não foi possível ler ruleset canônico"
  ruleset_matches_payload "$current" \
    || fail "ruleset canônico diverge do baseline fail-closed"
}

reconcile_ruleset() {
  local ids count
  ids="$(find_ruleset_ids)" || fail "não foi possível listar rulesets para reconciliação"
  count="$(count_ruleset_ids "$ids")"
  [ "$count" -eq 1 ] || fail "esperado exatamente um ruleset canônico após bootstrap; encontrados $count"
  validate_single_ruleset "$ids"
}

wait_for_concurrent_owner() {
  local tentativa ids count
  aviso "lock remoto já existe; aguardando owner concluir e reconciliando estado"
  for ((tentativa=1; tentativa<=LOCK_WAIT_ATTEMPTS; tentativa++)); do
    ids="$(find_ruleset_ids)" || fail "não foi possível listar rulesets durante espera do lock remoto"
    count="$(count_ruleset_ids "$ids")"
    if [ "$count" -gt 1 ]; then
      fail "mais de um ruleset canônico apareceu durante concorrência; intervenção administrativa necessária"
    fi
    if [ "$count" -eq 1 ]; then
      validate_single_ruleset "$ids"
      ok "concorrente concluiu ruleset canônico íntegro sob lock remoto"
      return 0
    fi
    sleep "$LOCK_WAIT_SECONDS"
  done
  fail "lock remoto existe sem ruleset canônico íntegro; possível lock stale, intervenção administrativa necessária"
}

existing_ids="$(find_ruleset_ids)" || fail "não foi possível listar rulesets existentes"
existing_count="$(count_ruleset_ids "$existing_ids")"
if [ "$existing_count" -gt 1 ]; then
  fail "mais de um ruleset com nome canônico; intervenção administrativa necessária"
fi
if [ "$existing_count" -eq 1 ]; then
  validate_single_ruleset "$existing_ids"
  ok "ruleset canônico já estava ativo e íntegro"
  exit 0
fi

# Serialização distribuída: a criação de uma Git ref fixa é atômica no GitHub.
# Apenas quem cria a ref pode entrar na seção crítica que contém o POST do ruleset.
# A ref é mantida como sentinela após sucesso; removê-la exigiria provar ownership.
lock_payload="$(jq -cn --arg ref "$LOCK_REF" --arg sha "$lock_sha" '{ref:$ref, sha:$sha}')"
if ! printf '%s' "$lock_payload" | gh api -X POST "$LOCK_REFS_ENDPOINT" \
    -H 'Accept: application/vnd.github+json' --input - >/dev/null 2>&1; then
  if gh api "$LOCK_REF_ENDPOINT" -H 'Accept: application/vnd.github+json' >/dev/null 2>&1; then
    wait_for_concurrent_owner
    exit 0
  fi
  fail "não foi possível adquirir lock remoto e a ref-sentinela não existe; falha de permissão/transporte"
fi

# Revalida dentro da seção crítica para cobrir criadores legados/administrativos
# que possam ter criado o ruleset entre a primeira leitura e a aquisição do lock.
existing_ids="$(find_ruleset_ids)" || fail "não foi possível reler rulesets após adquirir lock remoto"
existing_count="$(count_ruleset_ids "$existing_ids")"
if [ "$existing_count" -gt 1 ]; then
  fail "mais de um ruleset canônico após adquirir lock remoto; intervenção administrativa necessária"
fi
if [ "$existing_count" -eq 1 ]; then
  validate_single_ruleset "$existing_ids"
  ok "ruleset canônico foi criado concorrentemente e está íntegro"
  exit 0
fi

# POST cria política nova e aditiva. Não há PUT/PATCH/DELETE de branch protection.
if ! printf '%s' "$payload" | gh api -X POST "$RULESETS_API" \
    -H 'Accept: application/vnd.github+json' --input - >/dev/null; then
  aviso "POST não retornou resposta confiável; reconciliando estado efetivo"
fi

reconcile_ruleset
ok "ruleset fail-closed da main criado e confirmado sob lock remoto atômico"
