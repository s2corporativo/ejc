#!/usr/bin/env bash
# Autenticação efêmera do GitHub App usada exclusivamente pelo Check Run do
# fallback local. Este arquivo deve ser SOURCED por scripts/ci-fallback.sh.
#
# Segredos:
# - a chave privada NÃO fica no repositório e NÃO é impressa;
# - o installation token existe somente em memória e no ambiente do subprocesso;
# - nenhum token é persistido em disco.
set -euo pipefail

EJC_GITHUB_API_VERSION="${EJC_GITHUB_API_VERSION:-2026-03-10}"
_EJC_APP_TOKEN=""
_EJC_APP_TOKEN_ISSUED_AT=0
_EJC_APP_TOKEN_REFRESH_SECONDS="${EJC_APP_TOKEN_REFRESH_SECONDS:-2700}" # 45 min

_ejc_auth_fail() {
  printf '[github-app-auth] ERRO: %s\n' "$*" >&2
  return 1
}

_ejc_base64url() {
  openssl base64 -A | tr '+/' '-_' | tr -d '='
}

_ejc_validate_private_key() {
  local key="${EJC_FALLBACK_APP_PRIVATE_KEY_FILE:-}" real_key root uid mode
  [ -n "$key" ] || _ejc_auth_fail "EJC_FALLBACK_APP_PRIVATE_KEY_FILE ausente" || return 1
  [ -f "$key" ] || _ejc_auth_fail "arquivo de chave privada do GitHub App ausente" || return 1
  [ ! -L "$key" ] || _ejc_auth_fail "chave privada não pode ser symlink" || return 1

  real_key="$(realpath "$key" 2>/dev/null || true)"
  [ -n "$real_key" ] || _ejc_auth_fail "não foi possível canonicalizar o caminho da chave" || return 1
  root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
  case "$real_key" in
    "$root"|"$root"/*|/opt/ejc|/opt/ejc/*)
      _ejc_auth_fail "chave privada deve permanecer fora do repositório e da produção" || return 1
      ;;
  esac

  uid="$(stat -c %u "$real_key" 2>/dev/null || true)"
  [ "$uid" = "$(id -u)" ] || _ejc_auth_fail "chave privada deve pertencer ao usuário do fallback" || return 1
  mode="$(stat -c %a "$real_key" 2>/dev/null || true)"
  [[ "$mode" =~ ^[0-7]{3,4}$ ]] || _ejc_auth_fail "não foi possível validar permissões da chave privada" || return 1
  # Rejeita qualquer bit de grupo/outros. 0400/0600 são os formatos esperados;
  # 0500 também é tecnicamente restrito ao dono e permanece seguro.
  local perm=$((8#$mode))
  (( (perm & 0077) == 0 )) || _ejc_auth_fail "chave privada possui permissões de grupo/outros; use acesso somente do proprietário" || return 1

  printf '%s\n' "$real_key"
}

_ejc_mint_installation_token() {
  local app_id="${EJC_FALLBACK_APP_ID:-}"
  local installation_id="${EJC_FALLBACK_INSTALLATION_ID:-}"
  [[ "$app_id" =~ ^[1-9][0-9]*$ ]] || _ejc_auth_fail "EJC_FALLBACK_APP_ID inválido" || return 1
  [[ "$installation_id" =~ ^[1-9][0-9]*$ ]] || _ejc_auth_fail "EJC_FALLBACK_INSTALLATION_ID inválido" || return 1
  command -v openssl >/dev/null 2>&1 || _ejc_auth_fail "openssl ausente" || return 1
  command -v curl >/dev/null 2>&1 || _ejc_auth_fail "curl ausente" || return 1
  command -v jq >/dev/null 2>&1 || _ejc_auth_fail "jq ausente" || return 1

  local key now iat exp header payload unsigned signature jwt response token
  key="$(_ejc_validate_private_key)" || return 1
  now="$(date +%s)"
  iat=$((now - 60))
  exp=$((now + 540))
  header="$(printf '%s' '{"alg":"RS256","typ":"JWT"}' | _ejc_base64url)"
  payload="$(printf '{"iat":%d,"exp":%d,"iss":"%s"}' "$iat" "$exp" "$app_id" | _ejc_base64url)"
  unsigned="$header.$payload"
  signature="$(printf '%s' "$unsigned" | openssl dgst -sha256 -sign "$key" -binary | _ejc_base64url)" \
    || _ejc_auth_fail "falha ao assinar JWT do GitHub App" || return 1
  jwt="$unsigned.$signature"

  # --config - evita colocar JWT em argv/process list. A resposta é capturada
  # somente em memória; em erro não é impressa porque pode conter material de auth.
  response="$({
    printf 'silent\nshow-error\nfail\n'
    printf 'request = "POST"\n'
    printf 'url = "https://api.github.com/app/installations/%s/access_tokens"\n' "$installation_id"
    printf 'header = "Accept: application/vnd.github+json"\n'
    printf 'header = "X-GitHub-Api-Version: %s"\n' "$EJC_GITHUB_API_VERSION"
    printf 'header = "Authorization: Bearer %s"\n' "$jwt"
  } | curl --config - 2>/dev/null)" \
    || _ejc_auth_fail "não foi possível obter installation token do GitHub App" || return 1
  unset jwt unsigned signature

  token="$(printf '%s' "$response" | jq -r '.token // empty')"
  [ -n "$token" ] || _ejc_auth_fail "GitHub não retornou installation token" || return 1
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
