#!/usr/bin/env bash
set -euo pipefail

# Operação local-first do EJC.
# GitHub é opcional: edição, validação, snapshot e deploy usam apenas a cópia local/VPS.

ROOT="${EJC_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
WORK_ROOT="${EJC_WORK_ROOT:-/opt/ejc-worktrees}"
SNAPSHOT_ROOT="${EJC_SNAPSHOT_ROOT:-/opt/ejc-snapshots}"
CI_MODE="${EJC_CI_MODE:-full}"

log() { printf '\n[ejc-local] %s\n' "$*"; }
die() { printf '[ejc-local] ERRO: %s\n' "$*" >&2; exit 1; }

require_file() {
  [ -f "$1" ] || die "arquivo obrigatório ausente: $1"
}

source_id() {
  local base="${1:-$ROOT}"
  local git_sha=""
  if git -C "$base" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git_sha="$(git -C "$base" rev-parse HEAD 2>/dev/null || true)"
    if [ -n "$git_sha" ] && git -C "$base" diff --quiet --ignore-submodules HEAD -- 2>/dev/null \
      && git -C "$base" diff --cached --quiet --ignore-submodules HEAD -- 2>/dev/null; then
      printf '%s\n' "$git_sha"
      return 0
    fi
  fi

  command -v sha256sum >/dev/null 2>&1 || die "sha256sum ausente; não é possível gerar identidade local"

  # Hash somente de código/config versionável. Exclui segredos, dados, caches e artefatos.
  local digest
  digest="$(
    cd "$base"
    {
      for path in backend frontend scripts nginx docker-compose.yml; do
        [ -e "$path" ] || continue
        if [ -d "$path" ]; then
          find "$path" -type f \
            ! -path '*/node_modules/*' \
            ! -path '*/.venv/*' \
            ! -path '*/.ci-venv/*' \
            ! -path '*/__pycache__/*' \
            ! -path '*/dist/*' \
            ! -path '*/build/*' \
            ! -name '.env' ! -name '.env.*' \
            -print0
        else
          printf '%s\0' "$path"
        fi
      done
    } | sort -z | xargs -0 -r sha256sum | sha256sum | awk '{print $1}'
  )"
  [ -n "$digest" ] || die "falha ao gerar identidade local"
  printf 'local-%s\n' "${digest:0:40}"
}

snapshot_source() {
  local base="${1:-$ROOT}"
  local id ts dir archive
  id="$(source_id "$base")"
  ts="$(date +%Y%m%d_%H%M%S)"
  dir="$SNAPSHOT_ROOT/$ts-$id"
  archive="$dir/source.tar.gz"
  mkdir -p "$dir"

  log "Criando snapshot de código $id"
  tar -C "$base" -czf "$archive" \
    --exclude='.git' \
    --exclude='.env' --exclude='.env.*' \
    --exclude='node_modules' --exclude='*/node_modules' \
    --exclude='.venv' --exclude='*/.venv' \
    --exclude='.ci-venv' --exclude='*/.ci-venv' \
    --exclude='__pycache__' --exclude='*/__pycache__' \
    --exclude='dist' --exclude='*/dist' \
    --exclude='build' --exclude='*/build' \
    --exclude='backups' --exclude='*/backups' \
    --exclude='uploads' --exclude='*/uploads' \
    --exclude='data' --exclude='*/data' \
    backend frontend scripts nginx docker-compose.yml 2>/dev/null || die "snapshot falhou"

  printf '%s\n' "$id" > "$dir/source_id.txt"
  sha256sum "$archive" > "$dir/source.tar.gz.sha256"
  printf '%s\n' "$dir"
}

prepare_worktree() {
  local name="${1:-work-$(date +%Y%m%d-%H%M%S)}"
  [[ "$name" =~ ^[A-Za-z0-9._-]+$ ]] || die "nome de worktree inválido"
  local dest="$WORK_ROOT/$name"
  [ ! -e "$dest" ] || die "destino já existe: $dest"
  mkdir -p "$WORK_ROOT"

  if git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    log "Criando worktree Git local em $dest (sem acesso remoto)"
    git -C "$ROOT" worktree add --detach "$dest" HEAD
    git -C "$dest" switch -c "local/$name"
  else
    command -v rsync >/dev/null 2>&1 || die "sem .git e rsync ausente"
    log "Sem .git: criando cópia isolada via rsync em $dest"
    mkdir -p "$dest"
    rsync -a \
      --exclude='.git' --exclude='.env' --exclude='.env.*' \
      --exclude='node_modules' --exclude='.venv' --exclude='.ci-venv' \
      --exclude='__pycache__' --exclude='dist' --exclude='build' \
      --exclude='backups' --exclude='uploads' --exclude='data' \
      "$ROOT/" "$dest/"
  fi
  printf '%s\n' "$dest"
}

validate() {
  local base="${1:-$ROOT}"
  require_file "$base/scripts/ci-local.sh"
  log "Validando localmente em $base (modo $CI_MODE)"
  (cd "$base" && bash scripts/ci-local.sh "$CI_MODE")
}

deploy() {
  local base="${1:-$ROOT}"
  require_file "$base/scripts/ci-local.sh"
  require_file "$base/scripts/deploy_vps_safe.sh"
  require_file "$base/scripts/backup.sh"

  local id snap
  id="$(source_id "$base")"
  snap="$(snapshot_source "$base" | tail -1)"
  log "Snapshot pré-deploy: $snap"

  validate "$base"

  # O deploy seguro já faz backup, build, healthcheck e rollback. Aqui tornamos
  # obrigatória a prova de backup e fornecemos uma identidade mesmo sem Git/.GitHub.
  log "Publicando $id por deploy seguro local-first"
  (
    cd "$base"
    TARGET_SHA="$id" \
    APP_DIR="$base" \
    REQUIRE_PREDEPLOY_BACKUP=1 \
    bash scripts/deploy_vps_safe.sh
  )
}

status() {
  local base="${1:-$ROOT}"
  printf 'root=%s\n' "$base"
  printf 'source_id=%s\n' "$(source_id "$base")"
  printf 'github_required=false\n'
  printf 'ci_local=%s\n' "$([ -f "$base/scripts/ci-local.sh" ] && echo ok || echo ausente)"
  printf 'deploy_safe=%s\n' "$([ -f "$base/scripts/deploy_vps_safe.sh" ] && echo ok || echo ausente)"
}

usage() {
  cat <<'USAGE'
Uso: scripts/operacao-local-first.sh <comando> [argumento]

  status [dir]          mostra identidade e pré-requisitos locais
  prepare <nome>        cria worktree/cópia isolada sem depender de remoto
  snapshot [dir]        cria snapshot de código sem segredos/dados
  validate [dir]        roda scripts/ci-local.sh (EJC_CI_MODE=full por padrão)
  deploy [dir]          snapshot + CI local + backup obrigatório + deploy seguro

GitHub/Actions não são necessários para nenhum comando acima.
USAGE
}

case "${1:-}" in
  status)   status "${2:-$ROOT}" ;;
  prepare)  prepare_worktree "${2:-}" ;;
  snapshot) snapshot_source "${2:-$ROOT}" ;;
  validate) validate "${2:-$ROOT}" ;;
  deploy)   deploy "${2:-$ROOT}" ;;
  *) usage; [ -n "${1:-}" ] && exit 2 || true ;;
esac
