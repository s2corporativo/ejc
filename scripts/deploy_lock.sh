#!/usr/bin/env bash
# Mutex host-level do deploy EJC.
#
# PRODUÇÃO: caminho imutável /run/lock/ejc/deploy.lock. Não depende de HOME,
# XDG_RUNTIME_DIR, APP_DIR nem variável de ambiente. O workflow adquire o lock
# antes do rsync e o executor filho revalida o FD herdado.
#
# Este arquivo é sourceable e não altera opções `set` do caller.

EJC_DEPLOY_PRODUCTION_LOCK_ROOT="/run/lock/ejc"
EJC_DEPLOY_PRODUCTION_LOCK_FILE="$EJC_DEPLOY_PRODUCTION_LOCK_ROOT/deploy.lock"

_ejc_deploy_lock_error() {
  printf '[deploy-lock] ERRO: %s\n' "$*" >&2
  return 2
}

_ejc_deploy_lock_require_commands() {
  local cmd
  for cmd in flock stat readlink; do
    command -v "$cmd" >/dev/null 2>&1 \
      || { _ejc_deploy_lock_error "$cmd é obrigatório"; return 2; }
  done
}

_ejc_deploy_lock_stat_inode() {
  stat -Lc '%d:%i' -- "$1" 2>/dev/null
}

_ejc_deploy_lock_validate_metadata() {
  local docker_gid="$1" root_owner root_group root_mode file_owner file_group file_mode

  [ ! -L "$EJC_DEPLOY_PRODUCTION_LOCK_ROOT" ] \
    || { _ejc_deploy_lock_error "diretório do mutex não pode ser symlink"; return 2; }
  [ ! -L "$EJC_DEPLOY_PRODUCTION_LOCK_FILE" ] \
    || { _ejc_deploy_lock_error "arquivo do mutex não pode ser symlink"; return 2; }
  [ -d "$EJC_DEPLOY_PRODUCTION_LOCK_ROOT" ] \
    || { _ejc_deploy_lock_error "raiz do mutex não é diretório"; return 2; }
  [ -f "$EJC_DEPLOY_PRODUCTION_LOCK_FILE" ] \
    || { _ejc_deploy_lock_error "mutex não é arquivo regular"; return 2; }

  root_owner="$(stat -c %u "$EJC_DEPLOY_PRODUCTION_LOCK_ROOT")" || return 2
  root_group="$(stat -c %g "$EJC_DEPLOY_PRODUCTION_LOCK_ROOT")" || return 2
  root_mode="$(stat -c %a "$EJC_DEPLOY_PRODUCTION_LOCK_ROOT")" || return 2
  file_owner="$(stat -c %u "$EJC_DEPLOY_PRODUCTION_LOCK_FILE")" || return 2
  file_group="$(stat -c %g "$EJC_DEPLOY_PRODUCTION_LOCK_FILE")" || return 2
  file_mode="$(stat -c %a "$EJC_DEPLOY_PRODUCTION_LOCK_FILE")" || return 2

  [ "$root_owner" = "0" ] && [ "$root_group" = "$docker_gid" ] && [ "$root_mode" = "750" ] \
    || { _ejc_deploy_lock_error "raiz do mutex deve ser root:<docker-gid> 0750"; return 2; }
  [ "$file_owner" = "0" ] && [ "$file_group" = "$docker_gid" ] && [ "$file_mode" = "660" ] \
    || { _ejc_deploy_lock_error "arquivo do mutex deve ser root:<docker-gid> 0660"; return 2; }
}

_ejc_deploy_lock_prepare_production() {
  local docker_gid
  _ejc_deploy_lock_require_commands || return $?
  [ -S /var/run/docker.sock ] \
    || { _ejc_deploy_lock_error "/var/run/docker.sock ausente"; return 2; }
  docker_gid="$(stat -c %g /var/run/docker.sock 2>/dev/null)" \
    || { _ejc_deploy_lock_error "não foi possível obter GID do docker.sock"; return 2; }
  [[ "$docker_gid" =~ ^[0-9]+$ ]] \
    || { _ejc_deploy_lock_error "GID do docker.sock inválido"; return 2; }

  # O diretório NÃO é group-writable. Membros do grupo Docker conseguem abrir
  # o arquivo 0660, mas não podem renomear/unlinkar/substituir seu inode.
  if [ -e "$EJC_DEPLOY_PRODUCTION_LOCK_ROOT" ]; then
    [ ! -L "$EJC_DEPLOY_PRODUCTION_LOCK_ROOT" ] \
      || { _ejc_deploy_lock_error "diretório existente do mutex é symlink"; return 2; }
  else
    if [ "$(id -u)" -eq 0 ]; then
      install -d -m 0750 -o root -g "$docker_gid" "$EJC_DEPLOY_PRODUCTION_LOCK_ROOT" \
        || { _ejc_deploy_lock_error "não foi possível criar diretório do mutex"; return 2; }
    else
      command -v sudo >/dev/null 2>&1 \
        || { _ejc_deploy_lock_error "sudo é necessário para criar diretório do mutex"; return 2; }
      sudo -n install -d -m 0750 -o root -g "$docker_gid" "$EJC_DEPLOY_PRODUCTION_LOCK_ROOT" \
        || { _ejc_deploy_lock_error "não foi possível criar diretório do mutex"; return 2; }
    fi
  fi

  if [ -e "$EJC_DEPLOY_PRODUCTION_LOCK_FILE" ]; then
    [ ! -L "$EJC_DEPLOY_PRODUCTION_LOCK_FILE" ] \
      || { _ejc_deploy_lock_error "arquivo existente do mutex é symlink"; return 2; }
  else
    if [ "$(id -u)" -eq 0 ]; then
      install -m 0660 -o root -g "$docker_gid" /dev/null "$EJC_DEPLOY_PRODUCTION_LOCK_FILE" \
        || { _ejc_deploy_lock_error "não foi possível criar arquivo do mutex"; return 2; }
    else
      sudo -n install -m 0660 -o root -g "$docker_gid" /dev/null "$EJC_DEPLOY_PRODUCTION_LOCK_FILE" \
        || { _ejc_deploy_lock_error "não foi possível criar arquivo do mutex"; return 2; }
    fi
  fi

  _ejc_deploy_lock_validate_metadata "$docker_gid" || return $?
  EJC_DEPLOY_LOCK_ROOT_RESOLVED="$EJC_DEPLOY_PRODUCTION_LOCK_ROOT"
  EJC_DEPLOY_LOCK_FILE_RESOLVED="$EJC_DEPLOY_PRODUCTION_LOCK_FILE"
  export EJC_DEPLOY_LOCK_ROOT_RESOLVED EJC_DEPLOY_LOCK_FILE_RESOLVED
}

# Adquire ou revalida o lock fixo no FD 9. Retorna 75 quando ocupado.
ejc_deploy_lock_acquire_production() {
  local path_inode fd_inode inherited_target
  _ejc_deploy_lock_prepare_production || return $?

  path_inode="$(_ejc_deploy_lock_stat_inode "$EJC_DEPLOY_PRODUCTION_LOCK_FILE")" \
    || { _ejc_deploy_lock_error "não foi possível obter inode do mutex"; return 2; }

  if [ -n "${EJC_DEPLOY_LOCK_FD:-}" ]; then
    [ "$EJC_DEPLOY_LOCK_FD" = "9" ] \
      || { _ejc_deploy_lock_error "somente FD 9 é aceito como mutex herdado"; return 2; }
    [ -e "/proc/$$/fd/9" ] \
      || { _ejc_deploy_lock_error "EJC_DEPLOY_LOCK_FD=9 informado, mas FD não está aberto"; return 2; }
    inherited_target="$(readlink -f "/proc/$$/fd/9" 2>/dev/null)" \
      || { _ejc_deploy_lock_error "não foi possível resolver FD herdado"; return 2; }
    [ "$inherited_target" = "$EJC_DEPLOY_PRODUCTION_LOCK_FILE" ] \
      || { _ejc_deploy_lock_error "FD herdado aponta para caminho diferente do mutex canônico"; return 2; }
    fd_inode="$(_ejc_deploy_lock_stat_inode "/proc/$$/fd/9")" \
      || { _ejc_deploy_lock_error "não foi possível obter inode do FD herdado"; return 2; }
    [ "$fd_inode" = "$path_inode" ] \
      || { _ejc_deploy_lock_error "inode do FD herdado diverge do caminho canônico"; return 2; }
    flock -n 9 || return 75
    return 0
  fi

  exec 9>>"$EJC_DEPLOY_PRODUCTION_LOCK_FILE" \
    || { _ejc_deploy_lock_error "não foi possível abrir mutex canônico"; return 2; }
  fd_inode="$(_ejc_deploy_lock_stat_inode "/proc/$$/fd/9")" \
    || { _ejc_deploy_lock_error "não foi possível obter inode após abertura"; return 2; }
  [ "$fd_inode" = "$path_inode" ] \
    || { _ejc_deploy_lock_error "inode mudou durante abertura do mutex; execução recusada"; return 2; }
  [ "$(_ejc_deploy_lock_stat_inode "$EJC_DEPLOY_PRODUCTION_LOCK_FILE")" = "$fd_inode" ] \
    || { _ejc_deploy_lock_error "path do mutex mudou após abertura"; return 2; }

  flock -n 9 || return 75
  EJC_DEPLOY_LOCK_FD=9
  export EJC_DEPLOY_LOCK_FD
  return 0
}
