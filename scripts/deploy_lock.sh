#!/usr/bin/env bash
# Mutex host-level do deploy EJC.
#
# Este arquivo é SOURCEABLE de propósito: o workflow adquire o lock antes do
# rsync e mantém o mesmo file descriptor até o fim do deploy. O executor filho
# recebe o FD por herança e revalida caminho + flock antes de prosseguir.
#
# Não altera `set -e/-u` do caller.

EJC_DEPLOY_PRODUCTION_LOCK_ROOT="/run/lock/ejc"
EJC_DEPLOY_PRODUCTION_LOCK_FILE="$EJC_DEPLOY_PRODUCTION_LOCK_ROOT/deploy.lock"

_ejc_deploy_lock_error() {
  printf '[deploy-lock] ERRO: %s\n' "$*" >&2
  return 2
}

_ejc_deploy_lock_canon() {
  realpath -m -- "$1"
}

_ejc_deploy_lock_require_commands() {
  local cmd
  for cmd in flock realpath stat readlink; do
    command -v "$cmd" >/dev/null 2>&1 \
      || { _ejc_deploy_lock_error "$cmd é obrigatório"; return 2; }
  done
}

_ejc_deploy_lock_prepare_production() {
  local docker_gid root_owner root_group root_mode file_owner file_group file_mode

  [ "$EJC_DEPLOY_LOCK_ROOT_RESOLVED" = "$EJC_DEPLOY_PRODUCTION_LOCK_ROOT" ] \
    || { _ejc_deploy_lock_error "em /opt/ejc o mutex é fixo em $EJC_DEPLOY_PRODUCTION_LOCK_ROOT"; return 2; }
  [ "$EJC_DEPLOY_LOCK_FILE_RESOLVED" = "$EJC_DEPLOY_PRODUCTION_LOCK_FILE" ] \
    || { _ejc_deploy_lock_error "em /opt/ejc o arquivo de mutex é fixo em $EJC_DEPLOY_PRODUCTION_LOCK_FILE"; return 2; }
  [ -S /var/run/docker.sock ] \
    || { _ejc_deploy_lock_error "/var/run/docker.sock ausente"; return 2; }

  docker_gid="$(stat -c %g /var/run/docker.sock 2>/dev/null)" \
    || { _ejc_deploy_lock_error "não foi possível obter GID do docker.sock"; return 2; }
  [[ "$docker_gid" =~ ^[0-9]+$ ]] \
    || { _ejc_deploy_lock_error "GID do docker.sock inválido"; return 2; }

  # O diretório NÃO é group-writable. Assim, usuários do grupo Docker podem
  # abrir o arquivo 0660, mas não podem unlinkar/substituir seu inode.
  if [ "$(id -u)" -eq 0 ]; then
    install -d -m 0750 -o root -g "$docker_gid" "$EJC_DEPLOY_PRODUCTION_LOCK_ROOT" \
      || { _ejc_deploy_lock_error "não foi possível provisionar diretório do mutex"; return 2; }
    if [ ! -e "$EJC_DEPLOY_PRODUCTION_LOCK_FILE" ]; then
      install -m 0660 -o root -g "$docker_gid" /dev/null "$EJC_DEPLOY_PRODUCTION_LOCK_FILE" \
        || { _ejc_deploy_lock_error "não foi possível criar arquivo do mutex"; return 2; }
    fi
  else
    command -v sudo >/dev/null 2>&1 \
      || { _ejc_deploy_lock_error "sudo é necessário para provisionar o mutex host-level"; return 2; }
    sudo -n install -d -m 0750 -o root -g "$docker_gid" "$EJC_DEPLOY_PRODUCTION_LOCK_ROOT" \
      || { _ejc_deploy_lock_error "não foi possível provisionar diretório do mutex"; return 2; }
    if ! sudo -n test -e "$EJC_DEPLOY_PRODUCTION_LOCK_FILE"; then
      sudo -n install -m 0660 -o root -g "$docker_gid" /dev/null "$EJC_DEPLOY_PRODUCTION_LOCK_FILE" \
        || { _ejc_deploy_lock_error "não foi possível criar arquivo do mutex"; return 2; }
    fi
  fi

  [ ! -L "$EJC_DEPLOY_PRODUCTION_LOCK_ROOT" ] \
    || { _ejc_deploy_lock_error "diretório do mutex não pode ser symlink"; return 2; }
  [ ! -L "$EJC_DEPLOY_PRODUCTION_LOCK_FILE" ] \
    || { _ejc_deploy_lock_error "arquivo do mutex não pode ser symlink"; return 2; }
  [ -d "$EJC_DEPLOY_PRODUCTION_LOCK_ROOT" ] \
    || { _ejc_deploy_lock_error "raiz do mutex não é diretório"; return 2; }
  [ -f "$EJC_DEPLOY_PRODUCTION_LOCK_FILE" ] \
    || { _ejc_deploy_lock_error "mutex não é arquivo regular"; return 2; }

  root_owner="$(stat -c %u "$EJC_DEPLOY_PRODUCTION_LOCK_ROOT")"
  root_group="$(stat -c %g "$EJC_DEPLOY_PRODUCTION_LOCK_ROOT")"
  root_mode="$(stat -c %a "$EJC_DEPLOY_PRODUCTION_LOCK_ROOT")"
  file_owner="$(stat -c %u "$EJC_DEPLOY_PRODUCTION_LOCK_FILE")"
  file_group="$(stat -c %g "$EJC_DEPLOY_PRODUCTION_LOCK_FILE")"
  file_mode="$(stat -c %a "$EJC_DEPLOY_PRODUCTION_LOCK_FILE")"

  [ "$root_owner" = "0" ] && [ "$root_group" = "$docker_gid" ] && [ "$root_mode" = "750" ] \
    || { _ejc_deploy_lock_error "metadados da raiz do mutex divergentes do contrato root:docker/0750"; return 2; }
  [ "$file_owner" = "0" ] && [ "$file_group" = "$docker_gid" ] && [ "$file_mode" = "660" ] \
    || { _ejc_deploy_lock_error "metadados do arquivo do mutex divergentes do contrato root:docker/0660"; return 2; }
}

_ejc_deploy_lock_prepare_nonproduction() {
  local app_canon="$1"
  [ ! -L "$EJC_DEPLOY_LOCK_ROOT" ] \
    || { _ejc_deploy_lock_error "EJC_DEPLOY_LOCK_ROOT não pode ser symlink"; return 2; }
  [ ! -L "$EJC_DEPLOY_LOCK_FILE" ] \
    || { _ejc_deploy_lock_error "EJC_DEPLOY_LOCK_FILE não pode ser symlink"; return 2; }
  case "$EJC_DEPLOY_LOCK_ROOT_RESOLVED" in
    /|"$app_canon"|"$app_canon"/*|/opt/ejc|/opt/ejc/*)
      _ejc_deploy_lock_error "raiz do mutex deve ficar fora de APP_DIR e /opt/ejc: $EJC_DEPLOY_LOCK_ROOT_RESOLVED"
      return 2
      ;;
  esac
  [[ "$EJC_DEPLOY_LOCK_FILE_RESOLVED" == "$EJC_DEPLOY_LOCK_ROOT_RESOLVED/"* ]] \
    || { _ejc_deploy_lock_error "arquivo de mutex deve ser descendente da raiz dedicada"; return 2; }

  mkdir -p "$EJC_DEPLOY_LOCK_ROOT_RESOLVED" \
    || { _ejc_deploy_lock_error "não foi possível criar raiz do mutex de teste"; return 2; }
  chmod 700 "$EJC_DEPLOY_LOCK_ROOT_RESOLVED" \
    || { _ejc_deploy_lock_error "não foi possível restringir raiz do mutex de teste"; return 2; }
  if [ ! -e "$EJC_DEPLOY_LOCK_FILE_RESOLVED" ]; then
    (umask 077 && : > "$EJC_DEPLOY_LOCK_FILE_RESOLVED") \
      || { _ejc_deploy_lock_error "não foi possível criar mutex de teste"; return 2; }
  fi
  chmod 600 "$EJC_DEPLOY_LOCK_FILE_RESOLVED" \
    || { _ejc_deploy_lock_error "não foi possível restringir mutex de teste"; return 2; }
  [ ! -L "$EJC_DEPLOY_LOCK_FILE_RESOLVED" ] \
    || { _ejc_deploy_lock_error "arquivo de mutex não pode ser symlink"; return 2; }
}

# Prepara a identidade canônica do mutex, mas ainda não adquire flock.
ejc_deploy_lock_prepare() {
  local app_dir="${1:-/opt/ejc}" app_canon
  _ejc_deploy_lock_require_commands || return $?

  app_canon="$(_ejc_deploy_lock_canon "$app_dir")" || return 2
  EJC_DEPLOY_LOCK_ROOT="${EJC_DEPLOY_LOCK_ROOT:-$EJC_DEPLOY_PRODUCTION_LOCK_ROOT}"
  EJC_DEPLOY_LOCK_FILE="${EJC_DEPLOY_LOCK_FILE:-$EJC_DEPLOY_LOCK_ROOT/deploy.lock}"
  EJC_DEPLOY_LOCK_ROOT_RESOLVED="$(_ejc_deploy_lock_canon "$EJC_DEPLOY_LOCK_ROOT")" || return 2
  EJC_DEPLOY_LOCK_FILE_RESOLVED="$(_ejc_deploy_lock_canon "$EJC_DEPLOY_LOCK_FILE")" || return 2
  export EJC_DEPLOY_LOCK_ROOT EJC_DEPLOY_LOCK_FILE
  export EJC_DEPLOY_LOCK_ROOT_RESOLVED EJC_DEPLOY_LOCK_FILE_RESOLVED

  case "$app_canon" in
    /opt/ejc|/opt/ejc/*) _ejc_deploy_lock_prepare_production ;;
    *) _ejc_deploy_lock_prepare_nonproduction "$app_canon" ;;
  esac
}

# Adquire ou revalida o lock no FD 9. Retorna 75 quando ocupado.
ejc_deploy_lock_acquire() {
  local app_dir="${1:-/opt/ejc}" inherited_target
  ejc_deploy_lock_prepare "$app_dir" || return $?

  if [ -n "${EJC_DEPLOY_LOCK_FD:-}" ]; then
    [ "$EJC_DEPLOY_LOCK_FD" = "9" ] \
      || { _ejc_deploy_lock_error "somente FD 9 é aceito como mutex herdado"; return 2; }
    [ -e "/proc/$$/fd/9" ] \
      || { _ejc_deploy_lock_error "EJC_DEPLOY_LOCK_FD=9 informado, mas FD não está aberto"; return 2; }
    inherited_target="$(readlink -f "/proc/$$/fd/9" 2>/dev/null)" \
      || { _ejc_deploy_lock_error "não foi possível resolver FD herdado"; return 2; }
    [ "$inherited_target" = "$EJC_DEPLOY_LOCK_FILE_RESOLVED" ] \
      || { _ejc_deploy_lock_error "FD herdado aponta para outro arquivo: $inherited_target"; return 2; }
    # Se já veio locked no mesmo open-file-description, é idempotente. Se veio
    # apenas aberto, esta chamada adquire. Se outro inode/descritor detém o lock,
    # falha com 75. Portanto a variável de ambiente não é um bypass.
    flock -n 9 || return 75
    return 0
  fi

  exec 9>>"$EJC_DEPLOY_LOCK_FILE_RESOLVED" \
    || { _ejc_deploy_lock_error "não foi possível abrir mutex"; return 2; }
  flock -n 9 || return 75
  EJC_DEPLOY_LOCK_FD=9
  export EJC_DEPLOY_LOCK_FD
  return 0
}
