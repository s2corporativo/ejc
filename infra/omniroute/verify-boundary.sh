#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

fail() {
  printf 'ERRO: %s\n' "$1" >&2
  exit 1
}

runtime_targets=()
for path in backend/app frontend/src; do
  if [[ -e "$path" ]]; then
    runtime_targets+=("$path")
  fi
done

# Todas as variantes de compose da raiz (principal, staging, override...),
# descobertas dinamicamente — uma referência ao OmniRoute em qualquer uma
# delas acopla uma stack de runtime ao gateway de engenharia.
for path in docker-compose*.yml; do
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

grep -Fq 'JWT_SECRET: "${OMNIROUTE_JWT_SECRET:?' "$compose" \
  || fail "JWT_SECRET obrigatório não está protegido por variável local"

grep -Fq 'REQUIRE_API_KEY: "${OMNIROUTE_REQUIRE_API_KEY:-true}"' "$compose" \
  || fail "API de inferência não está com autenticação obrigatória por padrão"

if grep -Ein '(/opt/ejc|/var/run/docker\.sock|\.codex|\.claude|\.ssh|/root/|backend/app|frontend/src)' "$compose"; then
  fail "compose do OmniRoute contém mount/referência sensível ou acoplamento ao checkout"
fi

grep -Fq 'no-new-privileges:true' "$compose" \
  || fail "no-new-privileges não está habilitado"

grep -Fq 'cap_drop:' "$compose" \
  || fail "cap_drop não está configurado"
grep -Fq -- '- ALL' "$compose" \
  || fail "cap_drop ALL não está configurado"

# Contrato INF-02: serviço persistentemente reiniciado não pode encher o
# disco do host — rotação json-file 50m × 5 obrigatória.
grep -Fq 'x-logging: &omniroute-logging' "$compose" \
  || fail "política de rotação de logs ausente (INF-02: json-file 50m × 5)"
grep -Fq 'logging: *omniroute-logging' "$compose" \
  || fail "serviço omniroute sem logging: *omniroute-logging (INF-02)"

# Preflight de segredo: o dashboard jamais pode subir com o segredo público
# do modelo ou vazio (compose aceitaria e forjaria sessões admin conhecidas).
env_file='infra/omniroute/.env'
if [[ -f "$env_file" ]]; then
  jwt_valor="$(grep -E '^OMNIROUTE_JWT_SECRET=' "$env_file" | tail -1 | cut -d= -f2-)"
  jwt_valor="${jwt_valor//\"/}"
  jwt_valor="${jwt_valor//\'}"
  jwt_valor="${jwt_valor// /}"
  if [[ -z "$jwt_valor" || "$jwt_valor" == "CHANGE_ME_WITH_A_RANDOM_SECRET" ]]; then
    fail "OMNIROUTE_JWT_SECRET vazio ou placeholder; gere um segredo forte (SECURE_BOOTSTRAP.md §1)"
  fi
fi

printf 'OK: fronteira IA jurídica x engenharia preservada.\n'
printf 'OK: backend continua com ai_gateway.py próprio.\n'
printf 'OK: OmniRoute permanece isolado, loopback-only e sem mounts sensíveis.\n'
printf 'OK: dashboard exige JWT local e inferência exige API key por padrão.\n'
