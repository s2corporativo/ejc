#!/usr/bin/env bash
# EJC local-first: trabalho, checkpoint e CI continuam mesmo sem GitHub.
# GitHub/origin é sincronização secundária e best-effort; nunca é requisito
# para preservar o trabalho ou executar a validação local.
set -euo pipefail
umask 077

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[ -n "$ROOT" ] || { echo "ERRO: execute dentro de um checkout Git do EJC." >&2; exit 2; }
cd "$ROOT"

CMD="${1:-status}"
shift || true

PRODUCTION_DIR="${EJC_PRODUCTION_DIR:-/opt/ejc}"
RECOVERY_ROOT="${EJC_RECOVERY_ROOT:-${HOME:-/tmp}/.local/state/ejc-recovery}"
REMOTE="${EJC_GIT_REMOTE:-origin}"
REMOTE_TIMEOUT="${EJC_GIT_TIMEOUT:-8}"
AUTO_PUSH="${EJC_LOCAL_FIRST_AUTO_PUSH:-1}"
MAX_UNTRACKED_BYTES="${EJC_CHECKPOINT_MAX_FILE_BYTES:-26214400}"
CI_MODE="${EJC_LOCAL_CI_MODE:-full}"

repo_name="$(basename "$ROOT")"
STATE_DIR="$RECOVERY_ROOT/$repo_name"
CHECKPOINT_DIR="$STATE_DIR/checkpoints"
PENDING_TASK_DIR="$STATE_DIR/pending-tasks"
SYNCED_TASK_DIR="$STATE_DIR/synced-tasks"
mkdir -p "$CHECKPOINT_DIR" "$PENDING_TASK_DIR" "$SYNCED_TASK_DIR"
chmod 700 "$RECOVERY_ROOT" "$STATE_DIR" "$CHECKPOINT_DIR" "$PENDING_TASK_DIR" "$SYNCED_TASK_DIR" 2>/dev/null || true

log() { printf '[ejc-local-first] %s\n' "$*"; }
warn() { printf '[ejc-local-first] AVISO: %s\n' "$*" >&2; }
die() { printf '[ejc-local-first] ERRO: %s\n' "$*" >&2; exit 2; }

real_root="$(realpath "$ROOT" 2>/dev/null || printf '%s' "$ROOT")"
real_prod="$(realpath "$PRODUCTION_DIR" 2>/dev/null || printf '%s' "$PRODUCTION_DIR")"
assert_not_production() {
  if [ "$real_root" = "$real_prod" ] && [ "${EJC_ALLOW_PRODUCTION_WORKTREE:-0}" != "1" ]; then
    die "checkout atual é o diretório de produção ($real_prod). Desenvolvimento local-first é bloqueado aqui."
  fi
}

current_branch() {
  git symbolic-ref --quiet --short HEAD 2>/dev/null || printf 'DETACHED'
}

write_mode() {
  printf '%s\n' "$1" > "$STATE_DIR/mode"
  chmod 600 "$STATE_DIR/mode" 2>/dev/null || true
}

remote_available() {
  git remote get-url "$REMOTE" >/dev/null 2>&1 || return 1
  if command -v timeout >/dev/null 2>&1; then
    timeout "$REMOTE_TIMEOUT" git ls-remote --exit-code "$REMOTE" HEAD >/dev/null 2>&1
  else
    git ls-remote --exit-code "$REMOTE" HEAD >/dev/null 2>&1
  fi
}

sensitive_path() {
  local p="$1"
  printf '%s\n' "$p" | grep -Eiq '(^|/)(\.env($|\.)|[^/]*\.(pem|key|p12|pfx|jks|keystore)$|id_rsa($|\.)|id_ed25519($|\.)|[^/]*(credential|credentials|secret|secrets)[^/]*)'
}

register_task() {
  assert_not_production
  local title="${1:-}" scope="${2:-}" ts branch sha slug file
  [ -n "$title" ] || die "informe um título técnico para o registro local da tarefa."
  [ -n "$scope" ] || scope="Escopo registrado localmente durante indisponibilidade do GitHub; detalhar no relatório/Issue ao sincronizar."
  if printf '%s\n%s\n' "$title" "$scope" | grep -Eiq '(BEGIN (RSA|OPENSSH|PRIVATE) KEY|password[[:space:]]*=|secret[[:space:]]*=|token[[:space:]]*=|api[_-]?key[[:space:]]*=)'; then
    die "o registro local parece conter segredo. Registre somente escopo técnico, nunca credenciais."
  fi
  ts="$(date -u +'%Y%m%dT%H%M%SZ')"
  branch="$(current_branch)"
  sha="$(git rev-parse HEAD)"
  slug="$(printf '%s' "$title" | tr '[:upper:]' '[:lower:]' | tr -cs '[:alnum:]' '-' | sed 's/^-//;s/-$//' | cut -c1-48)"
  [ -n "$slug" ] || slug="tarefa"
  file="$PENDING_TASK_DIR/${ts}-${slug}.md"
  cat > "$file" <<EOF
# $title

- criado_em_utc: $ts
- branch: $branch
- sha_base: $sha
- origem: contingencia-local-first
- sincronizacao: pendente

## Escopo

$scope

## Regras

- não contém segredo, PII real ou documento de cliente;
- deve ser convertido/vinculado a Issue e PR quando o GitHub estiver disponível;
- o registro local não autoriza bypass de testes, revisão, backup, rollback ou proteção de produção.
EOF
  chmod 600 "$file" 2>/dev/null || true
  printf '%s\n' "$file" > "$STATE_DIR/last-task"
  log "tarefa registrada localmente: $file"
}

sync_pending_tasks() {
  local task title output destination
  command -v gh >/dev/null 2>&1 || { warn "gh ausente; registros locais de tarefa permanecem pendentes para sincronização posterior."; return 0; }
  if command -v timeout >/dev/null 2>&1; then
    timeout "$REMOTE_TIMEOUT" gh auth status >/dev/null 2>&1 || { warn "gh sem autenticação utilizável; registros de tarefa permanecem locais."; return 0; }
  else
    gh auth status >/dev/null 2>&1 || { warn "gh sem autenticação utilizável; registros de tarefa permanecem locais."; return 0; }
  fi

  while IFS= read -r -d '' task; do
    title="$(sed -n '1s/^# //p' "$task")"
    [ -n "$title" ] || { warn "registro local sem título válido: $task"; continue; }
    if command -v timeout >/dev/null 2>&1; then
      output="$(timeout "$REMOTE_TIMEOUT" gh issue create --title "$title" --body-file "$task" 2>/dev/null || true)"
    else
      output="$(gh issue create --title "$title" --body-file "$task" 2>/dev/null || true)"
    fi
    if printf '%s' "$output" | grep -Eq '^https?://'; then
      destination="$SYNCED_TASK_DIR/$(basename "$task")"
      mv "$task" "$destination"
      printf '%s\n' "$output" > "$destination.issue-url"
      chmod 600 "$destination" "$destination.issue-url" 2>/dev/null || true
      log "registro local sincronizado como Issue: $output"
    else
      warn "não foi possível criar Issue para $(basename "$task"); registro permanece pendente."
    fi
  done < <(find "$PENDING_TASK_DIR" -maxdepth 1 -type f -name '*.md' -print0 | sort -z)
}

checkpoint() {
  assert_not_production
  local ts sha short dir list safe_list skipped size file
  ts="$(date -u +'%Y%m%dT%H%M%SZ')"
  sha="$(git rev-parse HEAD)"
  short="$(git rev-parse --short=12 HEAD)"
  dir="$CHECKPOINT_DIR/${ts}-${short}"
  mkdir -p "$dir"
  chmod 700 "$dir"

  printf '%s\n' "$sha" > "$dir/base-sha.txt"
  current_branch > "$dir/branch.txt"
  printf '%s\n' "$ROOT" > "$dir/source-root.txt"
  git status --porcelain=v1 > "$dir/status.txt"
  git diff --binary HEAD > "$dir/tracked-working-tree.patch"
  git diff --cached --binary > "$dir/index.patch"

  list="$dir/untracked-all.list0"
  safe_list="$dir/untracked-safe.list0"
  skipped="$dir/skipped-untracked.txt"
  : > "$list"; : > "$safe_list"; : > "$skipped"
  git ls-files --others --exclude-standard -z > "$list"

  while IFS= read -r -d '' file; do
    if sensitive_path "$file"; then
      printf '%s\n' "$file" >> "$skipped"
      continue
    fi
    if [ -L "$file" ]; then
      printf '%s\n' "$file (symlink)" >> "$skipped"
      continue
    fi
    if [ -f "$file" ]; then
      size="$(wc -c < "$file" 2>/dev/null || printf '0')"
      if [ "$size" -gt "$MAX_UNTRACKED_BYTES" ]; then
        printf '%s\n' "$file (>${MAX_UNTRACKED_BYTES} bytes)" >> "$skipped"
        continue
      fi
      printf '%s\0' "$file" >> "$safe_list"
    fi
  done < "$list"

  if [ -s "$safe_list" ]; then
    tar --null -T "$safe_list" -czf "$dir/untracked-safe.tar.gz"
  fi

  # Bundle contém somente histórico já commitado; working tree fica nos patches/tar locais.
  git bundle create "$dir/repository.bundle" --branches --tags >/dev/null 2>&1 || \
    git bundle create "$dir/repository.bundle" HEAD >/dev/null 2>&1

  rm -f "$list" "$safe_list"
  (
    cd "$dir"
    find . -maxdepth 1 -type f ! -name 'SHA256SUMS' -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
  )
  chmod 600 "$dir"/* 2>/dev/null || true
  printf '%s\n' "$dir" > "$STATE_DIR/last-checkpoint"

  log "checkpoint local criado: $dir"
  if [ -s "$skipped" ]; then
    warn "arquivos não rastreados potencialmente sensíveis/grandes foram deliberadamente excluídos do snapshot; os nomes estão em skipped-untracked.txt."
  fi
}

validate() {
  assert_not_production
  local mode="${1:-$CI_MODE}"
  [ -x scripts/ci-local.sh ] || die "scripts/ci-local.sh ausente ou não executável."
  checkpoint
  log "executando CI local: scripts/ci-local.sh $mode"
  scripts/ci-local.sh "$mode"
  log "CI local verde."
}

sync_remote() {
  assert_not_production
  checkpoint
  local branch ahead behind counts
  branch="$(current_branch)"

  if ! remote_available; then
    write_mode offline
    warn "Git remoto indisponível. Modo OFFLINE ativado; checkpoint e CI local continuam válidos."
    return 0
  fi

  if ! git fetch --prune "$REMOTE"; then
    write_mode offline
    warn "fetch falhou. Modo OFFLINE preservado; nenhum reset/rebase foi executado."
    return 0
  fi
  write_mode online

  if [ "$branch" = "DETACHED" ]; then
    warn "HEAD destacado: fetch concluído, publicação automática bloqueada."
    sync_pending_tasks
    return 0
  fi
  if [ "$branch" = "main" ] || [ "$branch" = "master" ]; then
    warn "branch protegida '$branch': fetch concluído; push automático bloqueado."
    sync_pending_tasks
    return 0
  fi

  if git show-ref --verify --quiet "refs/remotes/$REMOTE/$branch"; then
    counts="$(git rev-list --left-right --count "$REMOTE/$branch...HEAD")"
    behind="${counts%%[[:space:]]*}"
    ahead="${counts##*[[:space:]]}"
    log "divergência $REMOTE/$branch: behind=$behind ahead=$ahead"
    if [ "$behind" != "0" ]; then
      warn "remoto avançou; não faço reset/rebase/merge automático. O trabalho local permanece preservado e pode continuar offline."
      sync_pending_tasks
      return 0
    fi
  else
    ahead="1"
    log "branch remota ainda não existe: $REMOTE/$branch"
  fi

  if [ "$AUTO_PUSH" = "1" ]; then
    if git push "$REMOTE" "HEAD:refs/heads/$branch"; then
      log "branch sincronizada sem force: $REMOTE/$branch"
    else
      write_mode offline
      warn "push falhou; tratado como indisponibilidade do GitHub. Trabalho preservado localmente."
      return 0
    fi
  else
    log "AUTO_PUSH=0: fetch concluído; publicação adiada."
  fi
  sync_pending_tasks
}

status_cmd() {
  local branch sha pending_count
  branch="$(current_branch)"
  sha="$(git rev-parse --short=12 HEAD)"
  pending_count="$(find "$PENDING_TASK_DIR" -maxdepth 1 -type f -name '*.md' | wc -l | tr -d ' ')"
  log "root=$ROOT"
  log "branch=$branch sha=$sha"
  log "recovery=$STATE_DIR pending_tasks=$pending_count"
  git status --short
  if remote_available; then
    write_mode online
    log "remoto '$REMOTE': disponível (mode=online)"
  else
    write_mode offline
    warn "remoto '$REMOTE': indisponível (mode=offline). Continue com register/checkpoint/validate; não bloqueie a tarefa por GitHub."
  fi
}

work() {
  local mode="${1:-$CI_MODE}"
  validate "$mode"
  sync_remote
  log "ciclo local-first concluído."
}

case "$CMD" in
  status) status_cmd ;;
  register) register_task "${1:-}" "${2:-}" ;;
  checkpoint) checkpoint ;;
  validate) validate "${1:-$CI_MODE}" ;;
  sync) sync_remote ;;
  work) work "${1:-$CI_MODE}" ;;
  *)
    cat >&2 <<'USAGE'
Uso: bash scripts/ejc-local-first.sh <comando> [argumentos]
  status                        mostra estado local e disponibilidade do remoto
  register "titulo" "escopo"    registra tarefa local quando Issue não puder ser criada
  checkpoint                    cria snapshot recuperável local, sem depender da rede
  validate [modo]               checkpoint + scripts/ci-local.sh (full|backend|frontend|fast)
  sync                          checkpoint + fetch/push/Issue best-effort, nunca force/rebase/reset
  work [modo]                   validate + sync; GitHub indisponível não interrompe o ciclo
USAGE
    exit 2
    ;;
esac
