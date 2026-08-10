#!/usr/bin/env bash
# Executa código de PR sob identidade Unix dedicada, sem credenciais do control
# plane. O controlador continua dono de gh/GitHub App/evidência/merge.
set -euo pipefail
umask 077

TRUST_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-}"
shift || true

WORKER_USER="${EJC_CI_WORKER_USER:-}"
WORKER_ROOT="${EJC_CI_WORKER_ROOT:-/var/tmp/ejc-ci-worker}"
SAFE_PATH="${EJC_CI_WORKER_PATH:-/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin}"
CONTROLLER_USER="$(id -un)"
CONTROLLER_UID="$(id -u)"

fail() { printf '[ci-worker] ERRO: %s\n' "$*" >&2; exit 1; }
log() { printf '[ci-worker] %s\n' "$*" >&2; }

canon() {
  if command -v realpath >/dev/null 2>&1; then realpath -m "$1"; else printf '%s\n' "$1"; fi
}

safe_remove_tree() {
  local path="$1" root path_real root_real
  root="$(canon "$WORKER_ROOT")"
  path_real="$(canon "$path")"
  root_real="$root"
  [[ "$path_real" == "$root_real/"* ]] || fail "limpeza recusada fora de WORKER_ROOT: $path_real"
  [ -d "$path_real" ] || return 0
  find "$path_real" -depth -mindepth 1 -delete
  rmdir "$path_real" 2>/dev/null || true
}

validate_common() {
  [ -n "$WORKER_USER" ] || fail "EJC_CI_WORKER_USER obrigatório"
  id "$WORKER_USER" >/dev/null 2>&1 || fail "usuário worker inexistente: $WORKER_USER"
  local worker_uid worker_groups root_real home_real
  worker_uid="$(id -u "$WORKER_USER")"
  [ "$worker_uid" -ne 0 ] || fail "worker não pode ser root"
  [ "$worker_uid" -ne "$CONTROLLER_UID" ] || fail "worker precisa de UID distinto do controlador"
  worker_groups="$(id -nG "$WORKER_USER")"
  if printf ' %s ' "$worker_groups" | grep -Eq ' (docker|sudo|wheel) '; then
    fail "worker pertence a grupo privilegiado: $worker_groups"
  fi

  for command_name in sudo git setfacl python3; do
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

  root_real="$(canon "$WORKER_ROOT")"
  home_real="$(canon "${HOME:-/__no_home__}")"
  case "$root_real" in
    /|"$home_real"|/opt/ejc|/opt/ejc/*|"$(canon "$TRUST_ROOT")"|"$(canon "$TRUST_ROOT")"/*)
      fail "EJC_CI_WORKER_ROOT deve ficar fora do repo, HOME raiz e produção: $root_real"
      ;;
  esac

  if [ -n "${EJC_FALLBACK_APP_PRIVATE_KEY_FILE:-}" ] && [ -e "$EJC_FALLBACK_APP_PRIVATE_KEY_FILE" ]; then
    if sudo -n -u "$WORKER_USER" -- test -r "$EJC_FALLBACK_APP_PRIVATE_KEY_FILE"; then
      fail "worker consegue ler a chave privada do GitHub App"
    fi
  fi

  local gh_cfg="${GH_CONFIG_DIR:-${HOME:-}/.config/gh}/hosts.yml"
  if [ -n "$gh_cfg" ] && [ -e "$gh_cfg" ] && sudo -n -u "$WORKER_USER" -- test -r "$gh_cfg"; then
    fail "worker consegue ler configuração autenticada do gh"
  fi
}

worker_runtime_preflight() {
  validate_common
  local command_name
  for command_name in bash python3.11 node npm psql pg_dump git; do
    sudo -n -u "$WORKER_USER" -- /usr/bin/env -i PATH="$SAFE_PATH" \
      /usr/bin/env bash -c 'command -v "$1" >/dev/null' _ "$command_name" \
      || fail "$command_name indisponível para worker"
  done
  local pyver node_major
  pyver="$(sudo -n -u "$WORKER_USER" -- /usr/bin/env -i PATH="$SAFE_PATH" python3.11 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  [ "$pyver" = "3.11" ] || fail "worker não possui Python 3.11"
  node_major="$(sudo -n -u "$WORKER_USER" -- /usr/bin/env -i PATH="$SAFE_PATH" node -p 'process.versions.node.split(".")[0]')"
  [ "$node_major" = "22" ] || fail "worker exige Node 22"

  # O worker não recebe Docker socket. Backend/continuity usam PostgreSQL local
  # efêmero sob o próprio UID; pgvector precisa estar instalado no host.
  sudo -n -u "$WORKER_USER" -- /usr/bin/env -i PATH="$SAFE_PATH" bash -c \
    'ls /usr/lib/postgresql/*/bin/initdb >/dev/null 2>&1' \
    || fail "PostgreSQL server local indisponível para worker"
  [ -n "$(find /usr/share/postgresql -path '*/extension/vector.control' -print -quit 2>/dev/null || true)" ] \
    || fail "extensão pgvector não instalada para PostgreSQL local"
  log "preflight aprovado: worker separado, sem sudo/Docker/credenciais do control plane"
}

prepare_stage_source() {
  local sha="$1" stage="$2" stage_root="$3" source_dir="$4" temp_ref
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

  mkdir -p "$stage_root/home" "$stage_root/state"
  chmod 0700 "$stage_root/home" "$stage_root/state"
  # Controlador continua proprietário. ACL concede rwX somente ao worker neste
  # snapshot efêmero; novos filhos mantêm ACL para worker e controlador.
  setfacl -Rm "u:${WORKER_USER}:rwX,u:${CONTROLLER_USER}:rwX" "$stage_root"
  setfacl -Rdm "u:${WORKER_USER}:rwx,u:${CONTROLLER_USER}:rwx" "$stage_root"
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

  mkdir -p "$WORKER_ROOT"
  chmod 0711 "$WORKER_ROOT"
  local stage_root="$WORKER_ROOT/${sha:0:12}-${stage}-$$"
  local source_dir="$stage_root/source"
  cleanup_stage() {
    set +e
    safe_remove_tree "$stage_root"
  }
  trap cleanup_stage EXIT INT TERM HUP

  prepare_stage_source "$sha" "$stage" "$stage_root" "$source_dir"

  # Ambiente zerado: nenhum GH_TOKEN, chave, HOME, SSH_AUTH_SOCK, XDG do
  # controlador ou variável secreta é herdada pelo código do PR.
  set +e
  sudo -n -u "$WORKER_USER" -- /usr/bin/env -i \
    HOME="$stage_root/home" \
    XDG_CACHE_HOME="$stage_root/state/cache" \
    PATH="$SAFE_PATH" \
    APP_ENV=development \
    EJC_ENV=development \
    EJC_ALLOW_PYTHON_MISMATCH=0 \
    EJC_CI_SOURCE_ROOT="$source_dir" \
    EJC_CI_STATE_ROOT="$stage_root/state" \
    EJC_CI_REPORT_ROOT="$stage_root/state/reports" \
    CI=1 \
    bash "$TRUST_ROOT/scripts/ci-local.sh" "$stage"
  rc=$?
  set -e
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
