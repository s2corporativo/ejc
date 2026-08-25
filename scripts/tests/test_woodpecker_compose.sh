#!/usr/bin/env bash
# Regressão da configuração Woodpecker: o segredo de autenticação deve existir
# nos dois lados e a identidade persistente do agente deve sobreviver a restart.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/infra/woodpecker/docker-compose.yml"

fail() {
  printf 'ERRO: %s\n' "$*" >&2
  exit 1
}

[ -f "$COMPOSE_FILE" ] || fail "compose do Woodpecker ausente"

server_block="$(
  awk '
    /^  woodpecker-server:/ {inside=1}
    /^  woodpecker-agent:/  {inside=0}
    inside {print}
  ' "$COMPOSE_FILE"
)"

agent_block="$(
  awk '
    /^  woodpecker-agent:/ {inside=1}
    /^volumes:/           {inside=0}
    inside {print}
  ' "$COMPOSE_FILE"
)"

grep -Fq -- '- WOODPECKER_AGENT_SECRET=${WOODPECKER_AGENT_SECRET}' <<<"$server_block"   || fail "servidor sem WOODPECKER_AGENT_SECRET; agentes não poderão autenticar"
grep -Fq -- '- WOODPECKER_GRPC_SECRET=${WOODPECKER_AGENT_SECRET}' <<<"$server_block"   || fail "servidor sem WOODPECKER_GRPC_SECRET persistente"
grep -Fq -- '- WOODPECKER_AGENT_SECRET=${WOODPECKER_AGENT_SECRET}' <<<"$agent_block"   || fail "agente sem WOODPECKER_AGENT_SECRET"
grep -Fq -- '- woodpecker-agent-config:/etc/woodpecker' <<<"$agent_block"   || fail "configuração/identidade do agente não está persistida"

printf 'Woodpecker compose: autenticação e persistência válidas.\n'
