#!/usr/bin/env bash
set -euo pipefail

# Operação local-first do EJC.
# GitHub é opcional para edição, checkpoint e validação. Produção NÃO é usada
# como workspace e não recebe código por este wrapper.

ROOT="${EJC_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
WORK_ROOT="${EJC_WORK_ROOT:-${XDG_STATE_HOME:-$HOME/.local/state}/ejc/worktrees}"
SNAPSHOT_ROOT="${EJC_SNAPSHOT_ROOT:-${XDG_STATE_HOME:-$HOME/.local/state}/ejc/snapshots}"
PROD_ROOT="${EJC_PROD_ROOT:-/opt/ejc}"
CI_MODE="${EJC_CI_MODE:-full}"

log() { printf '\n[ejc-local] %s\n' "$*"; }
die() { printf '[ejc-local] ERRO: %s\n' "$*" >&2; exit 1; }

require_file() {
  [ -f "$1" ] || die "arquivo obrigatório ausente: $1"
}

canon() {
  if command -v realpath >/dev/null 2>&1; then
    realpath -m "$1"
  else
    (cd "$1" 2>/dev/null && pwd -P) || printf '%s\n' "$1"
  fi
}

assert_not_production_workspace() {
  local base prod
  base="$(canon "$1")"
  prod="$(canon "$PROD_ROOT")"
  if [ "$base" = "$prod" ] || [[ "$base" == "$prod/"* ]]; then
    die "diretório produtivo não pode ser usado como workspace local-first: $base"
  fi
}

source_id() {
  local base="${1:-$ROOT}"
  assert_not_production_workspace "$base"

  local git_sha=""
  if git -C "$base" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git_sha="$(git -C "$base" rev-parse HEAD 2>/dev/null || true)"
    if [ -n "$git_sha" ] \
      && git -C "$base" diff --quiet --ignore-submodules HEAD -- 2>/dev/null \
      && git -C "$base" diff --cached --quiet --ignore-submodules HEAD -- 2>/dev/null; then
      printf '%s\n' "$git_sha"
      return 0
    fi
  fi

  command -v sha256sum >/dev/null 2>&1 || die "sha256sum ausente; não é possível gerar identidade local"

  # Com Git, hash de TODOS os arquivos versionados existentes. Isso evita que
  # uma mudança em docs/config/scripts relevantes fique fora da identidade e,
  # ao mesmo tempo, nunca inclui .env ou outro arquivo não versionado.
  local digest
  if git -C "$base" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    digest="$(
      cd "$base"
      git ls-files -z \
        | while IFS= read -r -d '' path; do
            [ -f "$path" ] || continue
            printf '%s\0' "$path"
            sha256sum "$path"
          done \
        | sha256sum | awk '{print $1}'
    )"
  else
    digest="$(
      cd "$base"
      {
        for path in backend frontend scripts nginx config docs docker-compose.yml; do
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
  fi
  [ -n "$digest" ] || die "falha ao gerar identidade local"
  printf 'local-%s\n' "${digest:0:40}"
}

snapshot_source() {
  local base="${1:-$ROOT}"
  assert_not_production_workspace "$base"

  local id ts dir archive
  id="$(source_id "$base")"
  ts="$(date +%Y%m%d_%H%M%S)"
  dir="$SNAPSHOT_ROOT/$ts-$id"
  archive="$dir/source.tar.gz"
  mkdir -p "$dir"

  log "Criando checkpoint de código $id"
  if git -C "$base" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    # Snapshot versionável: tracked files + alterações locais, nunca untracked
    # como .env/uploads. O tar comum abaixo preserva a árvore atual dos tracked.
    local list="$dir/tracked-files.txt"
    git -C "$base" ls-files -z > "$list"
    tar --null -T "$list" -C "$base" -czf "$archive" \
      || die "checkpoint Git falhou"
  else
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
      backend frontend scripts nginx config docs docker-compose.yml 2>/dev/null \
      || die "checkpoint sem Git falhou"
  fi

  printf '%s\n' "$id" > "$dir/source_id.txt"
  sha256sum "$archive" > "$dir/source.tar.gz.sha256"
  printf '%s\n' "$dir"
}

prepare_worktree() {
  assert_not_production_workspace "$ROOT"

  local name="${1:-work-$(date +%Y%m%d-%H%M%S)}"
  [[ "$name" =~ ^[A-Za-z0-9._-]+$ ]] || die "nome de worktree inválido"
  local dest="$WORK_ROOT/$name"
  [ ! -e "$dest" ] || die "destino já existe: $dest"
  mkdir -p "$WORK_ROOT"
  assert_not_production_workspace "$dest"

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
  assert_not_production_workspace "$base"
  require_file "$base/scripts/ci-local.sh"
  log "Validando localmente em $base (modo $CI_MODE)"
  (cd "$base" && bash scripts/ci-local.sh "$CI_MODE")
}

sync_remote() {
  local base="${1:-$ROOT}"
  assert_not_production_workspace "$base"
  git -C "$base" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
    || die "sync exige repositório Git local"

  local branch
  branch="$(git -C "$base" branch --show-current)"
  [ -n "$branch" ] || die "sync exige branch local (não detached HEAD)"
  [ "$branch" != "main" ] && [ "$branch" != "master" ] \
    || die "sync não publica diretamente branch protegida"

  git -C "$base" diff --quiet --ignore-submodules HEAD -- \
    && git -C "$base" diff --cached --quiet --ignore-submodules HEAD -- \
    || die "há alterações sem commit; faça checkpoint/commit local antes do sync"

  if ! git -C "$base" remote get-url origin >/dev/null 2>&1; then
    die "remote origin ausente"
  fi

  log "Tentando sincronização não destrutiva com origin…"
  if ! git -C "$base" fetch --prune origin; then
    printf '[ejc-local] GitHub/origin indisponível; trabalho local preservado, sync pendente.\n' >&2
    return 75
  fi

  local remote_ref="refs/remotes/origin/$branch"
  if git -C "$base" show-ref --verify --quiet "$remote_ref"; then
    local local_sha remote_sha base_sha
    local_sha="$(git -C "$base" rev-parse HEAD)"
    remote_sha="$(git -C "$base" rev-parse "$remote_ref")"
    base_sha="$(git -C "$base" merge-base HEAD "$remote_ref")"
    if [ "$base_sha" != "$remote_sha" ]; then
      if [ "$base_sha" = "$local_sha" ]; then
        die "origin/$branch avançou; reconciliar em branch local antes de publicar"
      fi
      die "branch local e origin/$branch divergiram; force-push/rewrite proibidos"
    fi
  fi

  git -C "$base" push -u origin "HEAD:refs/heads/$branch"
  ok_id="$(source_id "$base")"
  printf '[ejc-local] sync concluído: %s\n' "$ok_id"
}

status() {
  local base="${1:-$ROOT}"
  printf 'root=%s\n' "$base"
  if [ "$(canon "$base")" = "$(canon "$PROD_ROOT")" ] || [[ "$(canon "$base")" == "$(canon "$PROD_ROOT")/"* ]]; then
    printf 'workspace_safe=false\n'
    printf 'source_id=indisponivel-em-producao\n'
  else
    printf 'workspace_safe=true\n'
    printf 'source_id=%s\n' "$(source_id "$base")"
  fi
  printf 'github_required_for_work=false\n'
  printf 'ci_local=%s\n' "$([ -f "$base/scripts/ci-local.sh" ] && echo ok || echo ausente)"
  printf 'sync_remote=opcional\n'
}

usage() {
  cat <<'USAGE'
Uso: scripts/operacao-local-first.sh <comando> [argumento]

  status [dir]          mostra identidade e segurança do workspace
  prepare <nome>        cria worktree/cópia isolada sem depender de remoto
  checkpoint [dir]      snapshot versionável sem segredos/dados
  snapshot [dir]        alias de checkpoint
  validate [dir]        roda scripts/ci-local.sh (EJC_CI_MODE=full por padrão)
  sync [dir]            tenta fetch/push normal; indisponibilidade remota => exit 75

Este wrapper NÃO faz deploy nem usa /opt/ejc como workspace. Produção continua
pela esteira segura já existente, depois de código validado e sincronizado.
USAGE
}

case "${1:-}" in
  status)     status "${2:-$ROOT}" ;;
  prepare)    prepare_worktree "${2:-}" ;;
  checkpoint) snapshot_source "${2:-$ROOT}" ;;
  snapshot)   snapshot_source "${2:-$ROOT}" ;;
  validate)   validate "${2:-$ROOT}" ;;
  sync)       sync_remote "${2:-$ROOT}" ;;
  *) usage; [ -n "${1:-}" ] && exit 2 || true ;;
esac
