#!/usr/bin/env bash
# Gera um installation access token efêmero para o GitHub App do CI fallback.
# O token é emitido somente em stdout para consumo imediato pelo processo pai;
# nunca é persistido, logado ou gravado em configuração do gh.
set -euo pipefail
umask 077

APP_ID="${EJC_FALLBACK_APP_ID:-}"
INSTALLATION_ID="${EJC_FALLBACK_APP_INSTALLATION_ID:-}"
PRIVATE_KEY_FILE="${EJC_FALLBACK_APP_PRIVATE_KEY_FILE:-}"
REPO="${EJC_REPO:-s2corporativo/ejc}"
API_URL="${GITHUB_API_URL:-https://api.github.com}"
API_VERSION="${EJC_GITHUB_API_VERSION:-2026-03-10}"

fail() {
  printf '[github-app-token] ERRO: %s\n' "$*" >&2
  exit 1
}

for command_name in openssl curl jq stat id; do
  command -v "$command_name" >/dev/null 2>&1 || fail "$command_name ausente"
done

[[ "$APP_ID" =~ ^[1-9][0-9]*$ ]] || fail "EJC_FALLBACK_APP_ID deve ser inteiro positivo"
[[ "$INSTALLATION_ID" =~ ^[1-9][0-9]*$ ]] || fail "EJC_FALLBACK_APP_INSTALLATION_ID deve ser inteiro positivo"
[[ "$REPO" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || fail "EJC_REPO inválido"
[ -n "$PRIVATE_KEY_FILE" ] || fail "EJC_FALLBACK_APP_PRIVATE_KEY_FILE não definido"
[ -f "$PRIVATE_KEY_FILE" ] || fail "arquivo da chave privada não existe"
[ ! -L "$PRIVATE_KEY_FILE" ] || fail "chave privada não pode ser symlink"
[ -r "$PRIVATE_KEY_FILE" ] || fail "chave privada não é legível"

key_uid="$(stat -c %u -- "$PRIVATE_KEY_FILE")"
[ "$key_uid" = "$(id -u)" ] || fail "chave privada deve pertencer ao usuário executor"
key_mode="$(stat -c %a -- "$PRIVATE_KEY_FILE")"
[[ "$key_mode" =~ ^[0-7]{3,4}$ ]] || fail "modo inválido da chave privada"
# Os últimos três dígitos são permissões POSIX. Grupo/outros devem ser zero.
perm_oct="${key_mode: -3}"
(( (8#$perm_oct & 077) == 0 )) || fail "chave privada deve ser inacessível a grupo/outros (ex.: 0600)"

repo_name="${REPO#*/}"
now="$(date +%s)"
iat=$((now - 60))
exp=$((now + 540))

base64url() {
  openssl base64 -A | tr '+/' '-_' | tr -d '='
}

header="$(printf '%s' '{"alg":"RS256","typ":"JWT"}' | base64url)"
payload_json="$(jq -cn --argjson iat "$iat" --argjson exp "$exp" --arg iss "$APP_ID" '{iat:$iat,exp:$exp,iss:$iss}')"
payload="$(printf '%s' "$payload_json" | base64url)"
unsigned="$header.$payload"
signature="$(printf '%s' "$unsigned" | openssl dgst -sha256 -sign "$PRIVATE_KEY_FILE" | base64url)"
jwt="$unsigned.$signature"

request_body="$(jq -cn --arg repo "$repo_name" '{repositories:[$repo],permissions:{checks:"write"}}')"
response_file="$(mktemp)"
cleanup() {
  rm -f "$response_file"
  unset jwt unsigned signature payload payload_json request_body
}
trap cleanup EXIT

http_code="$(curl --silent --show-error \
  --output "$response_file" \
  --write-out '%{http_code}' \
  --request POST \
  --header 'Accept: application/vnd.github+json' \
  --header "Authorization: Bearer $jwt" \
  --header "X-GitHub-Api-Version: $API_VERSION" \
  --header 'Content-Type: application/json' \
  --data "$request_body" \
  "$API_URL/app/installations/$INSTALLATION_ID/access_tokens")" \
  || fail "falha de transporte ao gerar installation token"

[ "$http_code" = "201" ] || {
  message="$(jq -r '.message // "resposta sem mensagem"' "$response_file" 2>/dev/null || printf 'resposta inválida')"
  fail "GitHub recusou installation token (HTTP $http_code): $message"
}

token="$(jq -er '.token | select(type == "string" and length > 20)' "$response_file" 2>/dev/null)" \
  || fail "resposta do GitHub não contém installation token válido"
printf '%s\n' "$token"
