#!/usr/bin/env bash
# Diagnóstico/recuperação limitada via API administrativa do Woodpecker.
# Nunca imprime PAT nem token de agente. Requer PAT somente em variável de ambiente local.
set -euo pipefail

fail() {
  printf 'ERRO: %s\n' "$*" >&2
  exit 1
}

for cmd in curl jq mktemp; do
  command -v "$cmd" >/dev/null 2>&1 || fail "$cmd ausente"
done

API_BASE="${WOODPECKER_API_URL:-https://ci.depaulateixeira.adv.br/api}"
API_TOKEN="${WOODPECKER_API_TOKEN:-}"
[ -n "$API_TOKEN" ] || fail "defina WOODPECKER_API_TOKEN localmente; não passe token por argumento ou chat"

AUTH_HEADER_FILE="$(mktemp)"
chmod 600 -- "$AUTH_HEADER_FILE"
printf 'Authorization: Bearer %s\n' "$API_TOKEN" >"$AUTH_HEADER_FILE"
unset API_TOKEN WOODPECKER_API_TOKEN

cleanup() {
  rm -f -- "$AUTH_HEADER_FILE"
}
trap cleanup EXIT

api_get() {
  curl -fsS \
    -H @"$AUTH_HEADER_FILE" \
    -H 'Accept: application/json' \
    "${API_BASE}$1"
}

api_patch_json() {
  local path="$1"
  local body="$2"
  curl -fsS -X PATCH \
    -H @"$AUTH_HEADER_FILE" \
    -H 'Accept: application/json' \
    -H 'Content-Type: application/json' \
    --data "$body" \
    "${API_BASE}${path}"
}

api_post_empty() {
  local path="$1"
  curl -fsS -X POST \
    -H @"$AUTH_HEADER_FILE" \
    -H 'Accept: application/json' \
    "${API_BASE}${path}"
}

show_agents() {
  api_get '/agents' | jq '[.[] | {
    id,
    name,
    no_schedule,
    capacity,
    last_contact,
    last_work,
    backend,
    platform,
    version,
    org_id,
    owner_id
  }]'
}

show_queue() {
  api_get '/pipelines' | jq '[.[] | {
    repo_id,
    number,
    status,
    branch,
    event,
    commit,
    created,
    started,
    finished
  }]'
}

show_repo() {
  local repo_id="$1"
  api_get "/repos/${repo_id}" | jq '{
    id,
    full_name,
    active,
    pr_enabled,
    require_approval,
    timeout,
    trusted
  }'
}

show_pipeline() {
  local repo_id="$1"
  local pipeline_number="$2"
  api_get "/repos/${repo_id}/pipelines/${pipeline_number}" | jq '{
    repo_id,
    number,
    status,
    event,
    branch,
    commit,
    created,
    started,
    finished,
    errors,
    workflows: [.workflows[]? | {
      id,
      name,
      state,
      agent_id,
      platform,
      started,
      finished,
      error
    }]
  }'
}

fix_schedule() {
  local agent_id="$1"
  local current
  current="$(api_get "/agents/${agent_id}" | jq '{id,name,no_schedule,capacity,last_contact,last_work,backend,platform,version,org_id,owner_id}')"

  local name no_schedule
  name="$(jq -r '.name // empty' <<<"$current")"
  no_schedule="$(jq -r '.no_schedule' <<<"$current")"
  [ -n "$name" ] || fail "agente ${agent_id} sem nome; não é seguro aplicar PATCH"

  printf 'Agente antes do ajuste:\n%s\n' "$current"
  if [ "$no_schedule" = "false" ]; then
    printf 'Agente já aceita agendamento; nenhuma alteração necessária.\n'
    return 0
  fi

  local body
  body="$(jq -nc --arg name "$name" '{name:$name,no_schedule:false}')"
  api_patch_json "/agents/${agent_id}" "$body" | jq '{
    id,
    name,
    no_schedule,
    capacity,
    last_contact,
    last_work,
    backend,
    platform,
    version,
    org_id,
    owner_id
  }'
}

restart_pipeline() {
  local repo_id="$1"
  local pipeline_number="$2"
  api_post_empty "/repos/${repo_id}/pipelines/${pipeline_number}" | jq '{
    repo_id,
    number,
    status,
    event,
    branch,
    commit,
    created,
    started,
    finished,
    rerun_count
  }'
}

usage() {
  cat <<'EOF'
Uso:
  diagnose-api.sh check [repo_id] [pipeline_number]
  diagnose-api.sh fix-schedule <agent_id>
  diagnose-api.sh restart-pipeline <repo_id> <pipeline_number>

Variáveis obrigatórias/aceitas:
  WOODPECKER_API_TOKEN   PAT administrativo local. Nunca é impresso.
  WOODPECKER_API_URL     default: https://ci.depaulateixeira.adv.br/api

O PAT é transferido para um arquivo temporário 0600 e removido da variável antes
das chamadas curl, evitando exposição do Bearer em argv/ps. O arquivo é apagado
automaticamente ao sair.

O comando check é read-only. fix-schedule altera somente name/no_schedule preservando
explicitamente o nome atual. restart-pipeline reexecuta um pipeline existente e deve
ser usado somente depois de existir agente apto/alocável.
EOF
}

case "${1:-check}" in
  check)
    printf '== Agentes ==\n'
    show_agents
    printf '== Fila global ==\n'
    show_queue
    if [ -n "${2:-}" ]; then
      printf '== Repositório %s ==\n' "$2"
      show_repo "$2"
    fi
    if [ -n "${2:-}" ] && [ -n "${3:-}" ]; then
      printf '== Pipeline %s/%s ==\n' "$2" "$3"
      show_pipeline "$2" "$3"
    fi
    ;;
  fix-schedule)
    [ -n "${2:-}" ] || fail "informe agent_id"
    fix_schedule "$2"
    ;;
  restart-pipeline)
    [ -n "${2:-}" ] && [ -n "${3:-}" ] || fail "informe repo_id e pipeline_number"
    restart_pipeline "$2" "$3"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
