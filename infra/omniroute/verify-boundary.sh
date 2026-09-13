#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

fail() {
  printf 'ERRO: %s\n' "$1" >&2
  exit 1
}

runtime_targets=()
for path in backend/app frontend/src docker-compose.yml docker-compose.prod.yml docker-compose.production.yml; do
  if [[ -e "$path" ]]; then
    runtime_targets+=("$path")
  fi
done

[[ -f backend/app/services/ai_gateway.py ]] || fail "gateway institucional backend/app/services/ai_gateway.py não encontrado"
[[ -f infra/omniroute/docker-compose.yml ]] || fail "compose isolado do OmniRoute não encontrado"

if ((${#runtime_targets[@]} > 0)); then
  if grep -RInE \
    --exclude='*.md' \
    --exclude-dir='node_modules' \
    --exclude-dir='__pycache__' \
    '(OMNIROUTE|ejc_omniroute|127\.0\.0\.1:20128|localhost:20128|OPENAI_BASE_URL[^[:cntrl:]]*20128|ANTHROPIC_BASE_URL[^[:cntrl:]]*20128)' \
    "${runtime_targets[@]}"; then
    fail "runtime jurídico contém referência ao OmniRoute; mantenha a integração restrita à engenharia"
  fi
fi

compose='infra/omniroute/docker-compose.yml'

grep -Fq '${OMNIROUTE_BIND_HOST:-127.0.0.1}:${OMNIROUTE_PORT:-20128}:20128' "$compose" \
  || fail "bind loopback padrão do OmniRoute foi removido ou alterado"

if grep -Ein '(/opt/ejc|/var/run/docker\.sock|\.codex|\.claude|\.ssh|/root/|backend/app|frontend/src)' "$compose"; then
  fail "compose do OmniRoute contém mount/referência sensível ou acoplamento ao checkout"
fi

grep -Fq 'no-new-privileges:true' "$compose" \
  || fail "no-new-privileges não está habilitado"

grep -Fq 'cap_drop:' "$compose" \
  || fail "cap_drop não está configurado"
grep -Fq -- '- ALL' "$compose" \
  || fail "cap_drop ALL não está configurado"

printf 'OK: fronteira IA jurídica x engenharia preservada.\n'
printf 'OK: backend continua com ai_gateway.py próprio.\n'
printf 'OK: OmniRoute permanece isolado, loopback-only e sem mounts sensíveis.\n'
