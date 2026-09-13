#!/usr/bin/env bash
# Recuperação operacional segura do Woodpecker server/agent na VPS.
# Não gera, altera, imprime ou copia segredos. Não remove volumes.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

fail() {
  printf 'ERRO: %s\n' "$*" >&2
  exit 1
}

for cmd in docker git curl awk stat mktemp seq; do
  command -v "$cmd" >/dev/null 2>&1 || fail "$cmd ausente"
done
docker compose version >/dev/null 2>&1 || fail "plugin docker compose ausente"

branch="$(git rev-parse --abbrev-ref HEAD)"
[ "$branch" = "main" ] || fail "execute somente a partir da branch main na VPS"
[ -z "$(git status --porcelain --untracked-files=no)" ] \
  || fail "há alterações versionadas locais; interrompendo para não sobrescrever estado"

git fetch origin main --quiet
local_head="$(git rev-parse HEAD)"
remote_head="$(git rev-parse origin/main)"
[ "$local_head" = "$remote_head" ] \
  || fail "clone da VPS não está no HEAD de origin/main; faça git pull --ff-only e rode novamente"

cd "$SCRIPT_DIR"
[ -f .env ] || fail ".env operacional ausente em infra/woodpecker"
[ ! -L .env ] || fail ".env não pode ser symlink"
[ "$(stat -c '%a' .env)" = "600" ] || fail ".env deve ter permissão 600"

rendered="$(mktemp)"
chmod 600 -- "$rendered"
cleanup() {
  rm -f -- "$rendered"
}
trap cleanup EXIT

docker compose config >"$rendered"

compose_value() {
  local key="$1"
  awk -v key="$key" '
    $1 == key ":" {
      sub(/^[^:]+:[[:space:]]*/, "")
      print
      exit
    }
  ' "$rendered"
}

agent_secret="$(compose_value WOODPECKER_AGENT_SECRET)"
grpc_secret="$(compose_value WOODPECKER_GRPC_SECRET)"
[ -n "$agent_secret" ] || fail "WOODPECKER_AGENT_SECRET não chegou ao compose renderizado"
[ -n "$grpc_secret" ] || fail "WOODPECKER_GRPC_SECRET não chegou ao compose renderizado"
[ "$agent_secret" != "$grpc_secret" ] \
  || fail "WOODPECKER_AGENT_SECRET e WOODPECKER_GRPC_SECRET devem ser diferentes"

# O mesmo WOODPECKER_AGENT_SECRET alimenta servidor e agente no compose canônico.
# Não rotacionar automaticamente: trocar o valor pode invalidar a identidade do agente.
cleanup
trap - EXIT

printf '1/5 Validando configuração...\n'
docker compose config --quiet

printf '2/5 Criando backup consistente dos volumes...\n'
bash backup.sh

printf '3/5 Atualizando imagens fixadas e recriando apenas server/agent...\n'
docker compose pull woodpecker-server woodpecker-agent
docker compose up -d --force-recreate woodpecker-server woodpecker-agent

printf '4/5 Aguardando servidor e agente estabilizarem...\n'
server_ok=0
agent_ok=0
for _ in $(seq 1 60); do
  if curl -fsS -o /dev/null http://127.0.0.1:8100/healthz; then
    server_ok=1
  fi

  agent_id="$(docker compose ps -q woodpecker-agent)"
  if [ -n "$agent_id" ]; then
    running="$(docker inspect --format '{{.State.Running}}' "$agent_id" 2>/dev/null || true)"
    health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$agent_id" 2>/dev/null || true)"
    if [ "$running" = "true" ] && { [ "$health" = "healthy" ] || [ "$health" = "none" ]; }; then
      agent_ok=1
    fi
  fi

  if [ "$server_ok" -eq 1 ] && [ "$agent_ok" -eq 1 ]; then
    break
  fi
  sleep 2
done

[ "$server_ok" -eq 1 ] || fail "healthz do woodpecker-server não estabilizou"
[ "$agent_ok" -eq 1 ] || fail "woodpecker-agent não permaneceu Running/healthy"

agent_id="$(docker compose ps -q woodpecker-agent)"
restart_count="$(docker inspect --format '{{.RestartCount}}' "$agent_id")"
[ "$restart_count" -le 1 ] || fail "woodpecker-agent reiniciou repetidamente após a recuperação"

agent_logs="$(docker compose logs --no-color --since=5m woodpecker-agent 2>&1 || true)"
if grep -Fq 'individual agent not found by token' <<<"$agent_logs"; then
  fail "agente ainda rejeitado pelo token; não altere segredos automaticamente — conferir o .env operacional em custódia"
fi
if grep -Fq 'error running agent' <<<"$agent_logs"; then
  fail "agente encerrou com erro; consultar logs locais na VPS sem publicar conteúdo sensível"
fi
if grep -Fq 'cannot load backend engine' <<<"$agent_logs"; then
  fail "backend Docker do agente não carregou; verificar socket/permissões locais"
fi

printf '5/5 Estado pós-recuperação:\n'
docker compose ps
printf 'Woodpecker server/agent estáveis localmente. Confirme agora que pipelines pendentes começaram a executar steps reais antes de liberar merges/deploys.\n'
