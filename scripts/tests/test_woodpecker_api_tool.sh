#!/usr/bin/env bash
# Contrato de segurança da ferramenta administrativa via API do Woodpecker.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO_ROOT/infra/woodpecker/diagnose-api.sh"

fail() {
  printf 'ERRO: %s\n' "$*" >&2
  exit 1
}

[ -f "$SCRIPT" ] || fail "diagnose-api.sh ausente"
bash -n "$SCRIPT"

grep -Fq 'WOODPECKER_API_TOKEN' "$SCRIPT" || fail "PAT não é lido de variável de ambiente"
grep -Fq 'https://ci.depaulateixeira.adv.br/api' "$SCRIPT" || fail "API canônica ausente"
grep -Fq "api_get '/agents'" "$SCRIPT" || fail "diagnóstico não lista agentes"
grep -Fq "api_get '/pipelines'" "$SCRIPT" || fail "diagnóstico não lista fila"
grep -Fq 'fix-schedule' "$SCRIPT" || fail "correção segura de no_schedule ausente"
grep -Fq "'{name:\$name,no_schedule:false}'" "$SCRIPT" || fail "PATCH não preserva nome ao liberar schedule"
grep -Fq 'restart-pipeline' "$SCRIPT" || fail "rerun controlado de pipeline ausente"

# O helper não deve fabricar/rotacionar agentes, reparar repositório ou executar operação destrutiva.
if grep -Eq 'POST[^\n]*/agents|DELETE|/repos/[^ ]*/repair|openssl rand|set -x' "$SCRIPT"; then
  fail "ferramenta API contém mutação fora do escopo seguro"
fi

# Nunca acessar/exibir token de agente devolvido pela API.
if grep -Eq '\.token|\["token"\]|\['"'"'token'"'"'\]' "$SCRIPT"; then
  fail "ferramenta API referencia token de agente"
fi

printf 'Woodpecker API tool: diagnóstico e mutações limitadas válidos.\n'
