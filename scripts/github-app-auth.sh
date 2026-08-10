#!/usr/bin/env bash
# Autenticação efêmera do GitHub App usada exclusivamente pelo Check Run do
# fallback local. Este arquivo deve ser SOURCED por scripts/ci-fallback.sh.
#
# Segurança:
# - a chave privada nunca entra no repositório e nunca é impressa;
# - o installation token existe somente em memória;
# - o token é limitado ao repositório EJC e à permissão checks:write;
# - o token é renovado antes do limite de 1 hora do GitHub.
set -euo pipefail
# O runner usa `printf ... | ejc_github_app_gh_api`. Sem lastpipe, a função roda
# em subshell e o token renovado se perde a cada chamada. Em scripts não
# interativos/job-control off, lastpipe mantém o último estágio no shell atual.
shopt -s lastpipe 2>/dev/null || true

EJC_GITHUB_API_VERSION="${EJC_GITHUB_API_VERSION:-2026-03-10}"
_EJC_APP_TOKEN=""
_EJC_APP_TOKEN_ISSUED_AT=0
_EJC_APP_TOKEN_REFRESH_SECONDS="${EJC_APP_TOKEN_REFRESH_SECONDS:-2700}"

_ejc_auth_fail() {
  printf '[github-app-auth] ERRO: %s\n' "$*" >&2
  return 1
}

_ejc_base64url() {
  openssl base64 -A | tr '+/' '-_' | tr -d '='
}

_ejc_validate_private_key() {
  local key="${EJC_FALLBACK_APP_PRIVATE_KEY_FILE:-}" real_key root uid mode perm

  [ -n "$key" ] || _ejc_auth_fail "EJC_FALLBACK_APP_PRIVATE_KEY_FILE ausente" || return 1
  [ -f "$key" ] || _ejc_auth_fail "arquivo de chave privada do GitHub App ausente" || return 1
  [ ! -L "$key" ] || _ejc_auth_fail "chave privada não pode ser symlink" || return 1
  [ -r "$key" ] || _ejc_auth_fail "chave privada não é legível" || return 1

  real_key="$(realpath "$key" 2>/dev/null || true)"
  [ -n "$real_key" ] || _ejc_auth_fail "não foi possível canonicalizar o caminho da chave" || return 1
  root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
  case "$real_key" in
    "$root"|"$root"/*|/opt/ejc|/opt/ejc/*)
      _ejc_auth_fail "chave privada deve permanecer fora do repositório e da produção" || return 1
      ;;
  esac

  uid="$(stat -c %u -- "$real_key" 2>/dev/null || true)"
  [ "$uid" = "$(id -u)" ] || _ejc_auth_fail "chave privada deve pertencer ao usuário do fallback" || return 1
  mode="$(stat -c %a -- "$real_key" 2>/dev/null || true)"
  [[ "$mode" =~ ^[0-7]{3,4}$ ]] || _ejc_auth_fail "não foi possível validar permissões da chave privada" || return 1
  perm=$((8#$mode))
  (( (perm & 0077) == 0 )) || _ejc_auth_fail "chave privada possui permissões de grupo/outros; use acesso somente do proprietário" || return 1

  printf '%s\n' "$real_key"
}

_ejc_validate_app_config() {
  local app_id="${EJC_FALLBACK_APP_ID:-}"
  local installation_id="${EJC_FALLBACK_APP_INSTALLATION_ID:-${EJC_FALLBACK_INSTALLATION_ID:-}}"
  local repo="${EJC_REPO:-s2corporativo/ejc}"

  [[ "$app_id" =~ ^[1-9][0-9]*$ ]] || _ejc_auth_fail "EJC_FALLBACK_APP_ID inválido" || return 1
  [[ "$installation_id" =~ ^[1-9][0-9]*$ ]] || _ejc_auth_fail "EJC_FALLBACK_APP_INSTALLATION_ID inválido" || return 1
  [[ "$repo" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || _ejc_auth_fail "EJC_REPO inválido" || return 1
}

_ejc_mint_installation_token() {
  _ejc_validate_app_config || return 1

  local app_id="${EJC_FALLBACK_APP_ID}"
  local installation_id="${EJC_FALLBACK_APP_INSTALLATION_ID:-${EJC_FALLBACK_INSTALLATION_ID:-}}"
  local repo="${EJC_REPO:-s2corporativo/ejc}"
  local repo_name="${repo#*/}"

  for command_name in openssl curl jq realpath stat id date; do
    command -v "$command_name" >/dev/null 2>&1 || _ejc_auth_fail "$command_name ausente" || return 1
  done

  local key now iat exp header payload unsigned signature jwt request_body response token
  key="$(_ejc_validate_private_key)" || return 1
  now="$(date +%s)"
  iat=$((now - 60))
  exp=$((now + 540))
  header="$(printf '%s' '{"alg":"RS256","typ":"JWT"}' | _ejc_base64url)"
  payload="$(jq -cn --argjson iat "$iat" --argjson exp "$exp" --arg iss "$app_id" \
    '{iat:$iat,exp:$exp,iss:$iss}' | _ejc_base64url)"
  unsigned="$header.$payload"
  signature="$(printf '%s' "$unsigned" | openssl dgst -sha256 -sign "$key" -binary | _ejc_base64url)" \
    || _ejc_auth_fail "falha ao assinar JWT do GitHub App" || return 1
  jwt="$unsigned.$signature"

  request_body="$(jq -cn --arg repo "$repo_name" \
    '{repositories:[$repo],permissions:{checks:"write"}}')"

  response="$({
    printf 'silent\nshow-error\nfail\n'
    printf 'request = "POST"\n'
    printf 'url = "https://api.github.com/app/installations/%s/access_tokens"\n' "$installation_id"
    printf 'header = "Accept: application/vnd.github+json"\n'
    printf 'header = "X-GitHub-Api-Version: %s"\n' "$EJC_GITHUB_API_VERSION"
    printf 'header = "Authorization: Bearer %s"\n' "$jwt"
    printf 'header = "Content-Type: application/json"\n'
    printf 'data = %s\n' "$(printf '%s' "$request_body" | jq -Rs .)"
  } | curl -q --config - 2>/dev/null)" \
    || _ejc_auth_fail "não foi possível obter installation token do GitHub App" || return 1

  unset jwt unsigned signature payload request_body
  token="$(printf '%s' "$response" | jq -er '.token | select(type == "string" and length > 20)' 2>/dev/null)" \
    || _ejc_auth_fail "GitHub não retornou installation token válido" || return 1
  printf '%s\n' "$token"
}

ejc_github_app_refresh() {
  local now
  now="$(date +%s)"
  if [ -n "$_EJC_APP_TOKEN" ] && [ $((now - _EJC_APP_TOKEN_ISSUED_AT)) -lt "$_EJC_APP_TOKEN_REFRESH_SECONDS" ]; then
    return 0
  fi
  _EJC_APP_TOKEN="$(_ejc_mint_installation_token)" || return 1
  _EJC_APP_TOKEN_ISSUED_AT="$now"
}

ejc_github_app_gh_api() {
  command -v gh >/dev/null 2>&1 || _ejc_auth_fail "gh ausente" || return 1
  ejc_github_app_refresh || return 1
  GH_TOKEN="$_EJC_APP_TOKEN" gh api "$@"
}

ejc_github_app_clear() {
  _EJC_APP_TOKEN=""
  _EJC_APP_TOKEN_ISSUED_AT=0
}
