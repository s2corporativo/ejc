#!/usr/bin/env bash
# Regressão da configuração Woodpecker: autenticação, persistência, versão e
# limites precisam sobreviver ao render real do Docker Compose.
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

grep -Fq -- 'image: woodpeckerci/woodpecker-server:v3.18.0' <<<"$server_block"   || fail "imagem do servidor não está fixada em v3.18.0"
grep -Fq -- 'image: woodpeckerci/woodpecker-agent:v3.18.0' <<<"$agent_block"   || fail "imagem do agente não está fixada na mesma versão do servidor"

grep -Fq -- '- WOODPECKER_AGENT_SECRET=${WOODPECKER_AGENT_SECRET:?' <<<"$server_block"   || fail "servidor sem WOODPECKER_AGENT_SECRET obrigatório"
grep -Fq -- '- WOODPECKER_GRPC_SECRET=${WOODPECKER_GRPC_SECRET:?' <<<"$server_block"   || fail "servidor sem WOODPECKER_GRPC_SECRET independente e obrigatório"
grep -Fq -- '- WOODPECKER_AGENT_SECRET=${WOODPECKER_AGENT_SECRET:?' <<<"$agent_block"   || fail "agente sem WOODPECKER_AGENT_SECRET obrigatório"
grep -Fq -- '- woodpecker-agent-config:/etc/woodpecker' <<<"$agent_block"   || fail "configuração/identidade do agente não está persistida"

grep -Fq -- '- WOODPECKER_BACKEND_DOCKER_LIMIT_MEM=${WOODPECKER_JOB_MEMORY_BYTES:-3221225472}' <<<"$agent_block"   || fail "jobs sem limite padrão de memória"
grep -Fq -- '- WOODPECKER_BACKEND_DOCKER_LIMIT_MEM_SWAP=${WOODPECKER_JOB_MEMORY_SWAP_BYTES:-3221225472}' <<<"$agent_block"   || fail "jobs sem limite padrão de memória+swap"
grep -Fq -- '- WOODPECKER_BACKEND_DOCKER_LIMIT_CPU_QUOTA=${WOODPECKER_JOB_CPU_QUOTA:-100000}' <<<"$agent_block"   || fail "jobs sem limite padrão de CPU"

command -v docker >/dev/null 2>&1 || fail "docker ausente; não é possível validar o compose renderizado"
docker compose version >/dev/null 2>&1 || fail "plugin docker compose ausente"

rendered="$(mktemp)"
cleanup() {
  [ -n "${rendered:-}" ] && [ -f "$rendered" ] && rm -f -- "$rendered"
}
trap cleanup EXIT

WOODPECKER_HOST=https://ci.example.invalid WOODPECKER_GITHUB_CLIENT=test-client WOODPECKER_GITHUB_SECRET=test-oauth-secret WOODPECKER_AGENT_SECRET=test-agent-secret WOODPECKER_GRPC_SECRET=test-grpc-secret   docker compose -f "$COMPOSE_FILE" config >"$rendered"

grep -Fq -- 'WOODPECKER_AGENT_SECRET: test-agent-secret' "$rendered"   || fail "segredo do agente não chegou à configuração renderizada"
grep -Fq -- 'WOODPECKER_GRPC_SECRET: test-grpc-secret' "$rendered"   || fail "segredo gRPC independente não chegou à configuração renderizada"
grep -Fq -- 'WOODPECKER_BACKEND_DOCKER_LIMIT_MEM: "3221225472"' "$rendered"   || fail "limite de memória não chegou à configuração renderizada"
grep -Fq -- 'WOODPECKER_BACKEND_DOCKER_LIMIT_CPU_QUOTA: "100000"' "$rendered"   || fail "limite de CPU não chegou à configuração renderizada"

printf 'Woodpecker compose: autenticação, versão, limites e persistência válidos.\n'
