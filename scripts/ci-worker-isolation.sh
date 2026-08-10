#!/usr/bin/env bash
# Executa código não confiável de PR sob identidade Unix dedicada, sem acesso às
# credenciais/evidência do control plane. Cada stage recebe snapshot Git novo.
set -euo pipefail
umask 077

TRUST_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-}"
shift || true

WORKER_USER="${EJC_CI_WORKER_USER:-}"
WORKER_ROOT="${EJC_CI_WORKER_ROOT:-/var/tmp/ejc-ci-worker}"
PG_MAJOR_REQUIRED="${EJC_CI_PG_MAJOR_REQUIRED:-16}"
PG_BIN_DIR="/usr/lib/postgresql/${PG_MAJOR_REQUIRED}/bin"
PG_EXTENSION_DIR="/usr/share/postgresql/${PG_MAJOR_REQUIRED}/extension"
BASE_SAFE_PATH="${EJC_CI_WORKER_PATH:-/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin}"
SAFE_PATH="$PG_BIN_DIR:$BASE_SAFE_PATH"
CONTROLLER_USER="$(id -un)"
CONTROLLER_UID="$(id -u)"
CONTROLLER_STATE_ROOT="${EJC_CI_STATE_ROOT:-}"

fail() { printf '[ci-worker] ERRO: %s\n' "$*" >&2; exit 1; }
log() { printf '[ci-worker] %s\n' "$*" >&2; }

canon() {
  if command -v realpath >/dev/null 2>&1; then realpath -m "$1"; else printf '%s\n' "$1"; fi
}

safe_remove_tree() {
  local path="$1" root_real path_real
  root_real="$(canon "$WORKER_ROOT")"
  path_real="$(canon "$path")"
  [[ "$path_real" == "$root_real/"* ]] || fail "limpeza recusada fora de WORKER_ROOT: $path_real"
  [ -d "$path_real" ] || return 0
  find "$path_real" -depth -mindepth 1 -delete
  rmdir "$path_real" 2>/dev/null || true
}

kill_worker_processes() {
  sudo -n -u "$WORKER_USER" -- /usr/bin/env -i PATH="$SAFE_PATH" \
    /bin/sh -c 'kill -KILL -1 2>/dev/null || true' >/dev/null 2>&1 || true
  sleep 0.1
  if pgrep -u "$WORKER_USER" >/dev/null 2>&1; then
    fail "processo residual do worker permaneceu ativo"
  fi
}

clean_worker_persistence() {
  local worker_uid
  worker_uid="$(id -u "$WORKER_USER")"
  for base in /tmp /dev/shm; do
    [ -d "$base" ] || continue
    sudo -n -u "$WORKER_USER" -- /usr/bin/env -i PATH="$SAFE_PATH" \
      find "$base" -xdev -uid "$worker_uid" -depth -delete >/dev/null 2>&1 || true
  done
  if command -v crontab >/dev/null 2>&1; then
    sudo -n -u "$WORKER_USER" -- /usr/bin/env -i PATH="$SAFE_PATH" crontab -r >/dev/null 2>&1 || true
  fi
}

validate_common() {
  [ -n "$WORKER_USER" ] || fail "EJC_CI_WORKER_USER obrigatório"
  [[ "$PG_MAJOR_REQUIRED" =~ ^[1-9][0-9]*$ ]] || fail "EJC_CI_PG_MAJOR_REQUIRED inválido"
  id "$WORKER_USER" >/dev/null 2>&1 || fail "usuário worker inexistente: $WORKER_USER"
  local worker_uid worker_groups root_real home_real passwd_home gh_cfg
  worker_uid="$(id -u "$WORKER_USER")"
  [ "$worker_uid" -ne 0 ] || fail "worker não pode ser root"
  [ "$worker_uid" -ne "$CONTROLLER_UID" ] || fail "worker precisa de UID distinto do controlador"
  worker_groups="$(id -nG "$WORKER_USER")"
  if printf ' %s ' "$worker_groups" | grep -Eq ' (docker|sudo|wheel|adm) '; then
    fail "worker pertence a grupo privilegiado: $worker_groups"
  fi

  for command_name in sudo git setfacl python3 pgrep getent; do
    command -v "$command_name" >/dev/null 2>&1 || fail "$command_name ausente"
  done
  sudo -n -u "$WORKER_USER" -- /usr/bin/env -i PATH="$SAFE_PATH" /usr/bin/true \
    || fail "controlador não consegue executar comando não interativo como worker"
  if sudo -n -u "$WORKER_USER" -- /usr/bin/env -i PATH="$SAFE_PATH" /usr/bin/sudo -n /usr/bin/true >/dev/null 2>&1; then
    fail "worker possui sudo não interativo; isolamento inválido"
  fi

  if [ -e /var/run/docker.sock ] && sudo -n -u "$WORKER_USER" -- test -r /var/run/docker.sock; then
    fail "worker consegue ler Docker socket"
  fi
  if [ -e /var/run/docker.sock ] && sudo -n -u "$WORKER_USER" -- test -w /var/run/docker.sock; then
    fail "worker consegue escrever no Docker socket"
  fi

  passwd_home="$(getent passwd "$WORKER_USER" | cut -d: -f6)"
  [ -n "$passwd_home" ] || fail "HOME cadastrado do worker não localizado"
  if [ -e "$passwd_home" ] && sudo -n -u "$WORKER_USER" -- test -w "$passwd_home"; then
    fail "HOME cadastrado do worker é gravável; use conta dedicada com HOME inexistente/read-only"
  fi

  root_real="$(canon "$WORKER_ROOT")"
  home_real="$(canon "${HOME:-/__no_home__}")"
  case "$root_real" in
    /|"$home_real"|/opt/ejc|/opt/ejc/*|"$(canon "$TRUST_ROOT")"|"$(canon "$TRUST_ROOT")"/*)
      fail "EJC_CI_WORKER_ROOT deve ficar fora do repo, HOME raiz e produção: $root_real"
      ;;
  esac

  if sudo -n -u "$WORKER_USER" -- test -w "$TRUST_ROOT"; then
    fail "worker consegue escrever no checkout do control plane"
  fi
  for trusted in \
    "$TRUST_ROOT/scripts/ci-local.sh" \
    "$TRUST_ROOT/scripts/ci-fallback.sh" \
    "$TRUST_ROOT/scripts/ci-worker-isolation.sh" \
    "$TRUST_ROOT/scripts/ci_evidence.py" \
    "$TRUST_ROOT/scripts/github-app-auth.sh"; do
    [ -e "$trusted" ] || fail "root of trust ausente: $trusted"
    if sudo -n -u "$WORKER_USER" -- test -w "$trusted"; then
      fail "worker consegue alterar root of trust: $trusted"
    fi
  done

  if [ -n "$CONTROLLER_STATE_ROOT" ] && [ -e "$CONTROLLER_STATE_ROOT" ]; then
    if sudo -n -u "$WORKER_USER" -- test -r "$CONTROLLER_STATE_ROOT"; then
      fail "worker consegue ler evidência/estado do control plane"
    fi
    if sudo -n -u "$WORKER_USER" -- test -w "$CONTROLLER_STATE_ROOT"; then
      fail "worker consegue escrever evidência/estado do control plane"
    fi
  fi

  if [ -n "${EJC_FALLBACK_APP_PRIVATE_KEY_FILE:-}" ] && [ -e "$EJC_FALLBACK_APP_PRIVATE_KEY_FILE" ]; then
    if sudo -n -u "$WORKER_USER" -- test -r "$EJC_FALLBACK_APP_PRIVATE_KEY_FILE"; then
      fail "worker consegue ler a chave privada do GitHub App"
    fi
  fi
  gh_cfg="${GH_CONFIG_DIR:-${HOME:-}/.config/gh}/hosts.yml"
  if [ -n "$gh_cfg" ] && [ -e "$gh_cfg" ] && sudo -n -u "$WORKER_USER" -- test -r "$gh_cfg"; then
    fail "worker consegue ler configuração autenticada do gh"
  fi
}

worker_runtime_preflight() {
  validate_common
  kill_worker_processes
  clean_worker_persistence

  [ "$PG_MAJOR_REQUIRED" = "16" ] || fail "fallback promovível do EJC exige PostgreSQL 16"
  [ -x "$PG_BIN_DIR/initdb" ] || fail "PostgreSQL 16 server não instalado em $PG_BIN_DIR"
  local latest_pg_dir extension command_name
  latest_pg_dir="$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1 || true)"
  [ "$latest_pg_dir" = "$PG_BIN_DIR" ] \
    || fail "runtime PostgreSQL efetivo divergente: esperado $PG_BIN_DIR, encontrado ${latest_pg_dir:-nenhum}"
  for extension in vector pg_trgm pgcrypto; do
    [ -f "$PG_EXTENSION_DIR/$extension.control" ] \
      || fail "extensão PostgreSQL 16 ausente: $extension"
  done

  for command_name in bash python3.11 node npm psql pg_dump git find; do
    sudo -n -u "$WORKER_USER" -- /usr/bin/env -i PATH="$SAFE_PATH" \
      /usr/bin/env bash -c 'command -v "$1" >/dev/null' _ "$command_name" \
      || fail "$command_name indisponível para worker"
  done
  if sudo -n -u "$WORKER_USER" -- /usr/bin/env -i PATH="$SAFE_PATH" bash -c 'command -v at >/dev/null 2>&1'; then
    fail "utilitário at disponível ao worker; remova/bloqueie agendamento persistente nessa conta dedicada"
  fi

  local pyver node_major psql_major pg_dump_major
  pyver="$(sudo -n -u "$WORKER_USER" -- /usr/bin/env -i PATH="$SAFE_PATH" python3.11 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  [ "$pyver" = "3.11" ] || fail "worker não possui Python 3.11"
  node_major="$(sudo -n -u "$WORKER_USER" -- /usr/bin/env -i PATH="$SAFE_PATH" node -p 'process.versions.node.split(".")[0]')"
  [ "$node_major" = "22" ] || fail "worker exige Node 22"
  psql_major="$(sudo -n -u "$WORKER_USER" -- /usr/bin/env -i PATH="$SAFE_PATH" psql --version | sed -E 's/.* ([0-9]+).*/\1/')"
  pg_dump_major="$(sudo -n -u "$WORKER_USER" -- /usr/bin/env -i PATH="$SAFE_PATH" pg_dump --version | sed -E 's/.* ([0-9]+).*/\1/')"
  [ "$psql_major" = "16" ] || fail "psql do worker não é versão 16"
  [ "$pg_dump_major" = "16" ] || fail "pg_dump do worker não é versão 16"

  log "preflight aprovado: UID separado, Python 3.11, Node 22, PostgreSQL 16+pgvector, sem sudo/Docker/credenciais"
}

prepare_stage_source() {
  local sha="$1" stage="$2" stage_root="$3" source_dir="$4" temp_ref trusted_ci writable
  [[ "$sha" =~ ^[0-9a-f]{40}$ ]] || fail "SHA inválido"
  temp_ref="refs/heads/__ejc_ci_${sha:0:12}_${stage}_$$"
  git -C "$TRUST_ROOT" cat-file -e "$sha^{commit}" || fail "SHA não existe no repositório controlador"
  git -C "$TRUST_ROOT" update-ref "$temp_ref" "$sha"
  trap 'git -C "$TRUST_ROOT" update-ref -d "${temp_ref:-}" >/dev/null 2>&1 || true' RETURN

  mkdir -p "$stage_root"
  chmod 0700 "$stage_root"
  git clone --quiet --no-hardlinks --single-branch --branch "${temp_ref#refs/heads/}" \
    "$TRUST_ROOT" "$source_dir" || fail "falha ao criar clone isolado do SHA"
  git -C "$source_dir" checkout --quiet --detach "$sha"
  git -C "$source_dir" branch -D "${temp_ref#refs/heads/}" >/dev/null 2>&1 || true
  git -C "$source_dir" remote remove origin >/dev/null 2>&1 || true
  [ "$(git -C "$source_dir" rev-parse HEAD)" = "$sha" ] || fail "clone isolado não corresponde ao SHA"
  git -C "$TRUST_ROOT" update-ref -d "$temp_ref"
  trap - RETURN

  mkdir -p "$stage_root/home" "$stage_root/state" "$stage_root/tmp"
  chmod 0700 "$stage_root/home" "$stage_root/state" "$stage_root/tmp"
  setfacl -m "u:${WORKER_USER}:rx,u:${CONTROLLER_USER}:rwx,m::rwx" "$stage_root"
  setfacl -m "u:${WORKER_USER}:rx,u:${CONTROLLER_USER}:rwx,m::rwx" "$source_dir"
  [ -d "$source_dir/scripts" ] || fail "snapshot sem diretório scripts"
  setfacl -m "u:${WORKER_USER}:rx,u:${CONTROLLER_USER}:rwx,m::rwx" "$source_dir/scripts"

  for writable in "$source_dir/backend" "$source_dir/frontend" "$stage_root/home" "$stage_root/state" "$stage_root/tmp"; do
    [ -d "$writable" ] || continue
    setfacl -Rm "u:${WORKER_USER}:rwX,u:${CONTROLLER_USER}:rwX,m::rwx" "$writable"
    setfacl -Rdm "u:${WORKER_USER}:rwx,u:${CONTROLLER_USER}:rwx,m::rwx" "$writable"
  done

  trusted_ci="$source_dir/scripts/.ejc-ci-local-controller.sh"
  cp "$TRUST_ROOT/scripts/ci-local.sh" "$trusted_ci"
  chmod 0555 "$trusted_ci"
  setfacl -m "u:${WORKER_USER}:rx,u:${CONTROLLER_USER}:rx,m::rx" "$trusted_ci"

  sudo -n -u "$WORKER_USER" -- test ! -w "$source_dir" || fail "worker consegue renomear itens na raiz do snapshot"
  sudo -n -u "$WORKER_USER" -- test ! -w "$source_dir/scripts" || fail "worker consegue substituir scripts trusted por directory write"
  sudo -n -u "$WORKER_USER" -- test ! -w "$trusted_ci" || fail "worker consegue escrever no ci-local trusted"
}

run_stage() {
  validate_common
  local sha="" stage=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --sha) sha="${2:-}"; shift 2 ;;
      --stage) stage="${2:-}"; shift 2 ;;
      *) fail "argumento inválido: $1" ;;
    esac
  done
  [[ "$sha" =~ ^[0-9a-f]{40}$ ]] || fail "--sha obrigatório"
  case "$stage" in
    backend|eval|frontend|p0|architecture|continuity|ui-extra) ;;
    *) fail "stage não permitido: $stage" ;;
  esac

  worker_runtime_preflight
  mkdir -p "$WORKER_ROOT"
  chmod 0711 "$WORKER_ROOT"
  local stage_root="$WORKER_ROOT/${sha:0:12}-${stage}-$$"
  local source_dir="$stage_root/source"
  local trusted_ci="$source_dir/scripts/.ejc-ci-local-controller.sh"

  cleanup_stage() {
    set +e
    kill_worker_processes || true
    clean_worker_persistence || true
    safe_remove_tree "$stage_root" || true
  }
  trap cleanup_stage EXIT INT TERM HUP

  prepare_stage_source "$sha" "$stage" "$stage_root" "$source_dir"

  set +e
  sudo -n -u "$WORKER_USER" -- /usr/bin/env -i \
    HOME="$stage_root/home" \
    TMPDIR="$stage_root/tmp" \
    XDG_CACHE_HOME="$stage_root/state/cache" \
    PATH="$SAFE_PATH" \
    GIT_CONFIG_COUNT=1 \
    GIT_CONFIG_KEY_0=safe.directory \
    GIT_CONFIG_VALUE_0="$source_dir" \
    APP_ENV=development \
    EJC_ENV=development \
    EJC_ALLOW_PYTHON_MISMATCH=0 \
    EJC_CI_STATE_ROOT="$stage_root/state" \
    EJC_CI_REPORT_ROOT="$stage_root/state/reports" \
    CI=1 \
    bash "$trusted_ci" "$stage"
  rc=$?
  set -e

  kill_worker_processes
  clean_worker_persistence
  return "$rc"
}

case "$MODE" in
  preflight)
    [ "$#" -eq 0 ] || fail "preflight não recebe argumentos"
    worker_runtime_preflight
    ;;
  run-stage)
    run_stage "$@"
    ;;
  *) fail "uso: $0 preflight | run-stage --sha SHA --stage STAGE" ;;
esac
