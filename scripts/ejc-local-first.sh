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

DEFAULT_PRODUCTION_DIR="/opt/ejc"
PRODUCTION_DIR="${EJC_PRODUCTION_DIR:-$DEFAULT_PRODUCTION_DIR}"
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
real_default_prod="$(realpath "$DEFAULT_PRODUCTION_DIR" 2>/dev/null || printf '%s' "$DEFAULT_PRODUCTION_DIR")"
assert_not_production() {
  if [ "$real_root" = "$real_default_prod" ] || [ "$real_root" = "$real_prod" ]; then
    die "checkout atual coincide com diretório de produção protegido ($real_root). O fluxo local-first não opera em produção."
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

contains_sensitive_text() {
  local text="$1"
  if printf '%s\n' "$text" | grep -Ei '(BEGIN (RSA|OPENSSH|EC|PRIVATE) KEY|password[[:space:]]*=|secret[[:space:]]*=|token[[:space:]]*=|api[-_]?key[[:space:]]*=)' >/dev/null; then
    return 0
  fi
  if printf '%s\n' "$text" | grep -Ei '([[:alnum:]._%+-]+@[[:alnum:].-]+\.[[:alpha:]]{2,}|[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2}|[0-9]{2}\.[0-9]{3}\.[0-9]{3}/[0-9]{4}-[0-9]{2}|\(?[0-9]{2}\)?[[:space:]-]?[0-9]{4,5}-[0-9]{4})' >/dev/null; then
    return 0
  fi
  return 1
}

register_task() {
  assert_not_production
  local title="${1:-}" scope="${2:-}" ts branch sha short_sha slug task_id file
  [ -n "$title" ] || die "informe um título técnico para o registro local da tarefa."
  [ -n "$scope" ] || scope="Escopo registrado localmente durante indisponibilidade do GitHub; detalhar no relatório/Issue ao sincronizar."
  if contains_sensitive_text "$title" || contains_sensitive_text "$scope"; then
    die "o registro local parece conter segredo ou PII. Registre somente escopo técnico anonimizado."
  fi
  ts="$(date -u +'%Y%m%dT%H%M%SZ')"
  branch="$(current_branch)"
  sha="$(git rev-parse HEAD)"
  short_sha="$(git rev-parse --short=12 HEAD)"
  slug="$(printf '%s' "$title" | tr '[:upper:]' '[:lower:]' | tr -cs '[:alnum:]' '-' | sed 's/^-//;s/-$//' | cut -c1-48)"
  [ -n "$slug" ] || slug="tarefa"
  task_id="${ts}-${short_sha}-${slug}-${BASHPID}-${RANDOM}"
  file="$PENDING_TASK_DIR/${task_id}.md"
  cat > "$file" <<EOF
# $title

- local_task_id: $task_id
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
  chmod 600 "$STATE_DIR/last-task" 2>/dev/null || true
  log "tarefa registrada localmente: $file"
}

find_existing_issue() {
  local marker="$1" result
  [ -n "$marker" ] || return 0
  command -v jq >/dev/null 2>&1 || return 0
  if command -v timeout >/dev/null 2>&1; then
    result="$(timeout "$REMOTE_TIMEOUT" gh issue list --state all --search "$marker in:body" --limit 20 --json url,body 2>/dev/null | jq -r --arg marker "$marker" '[.[] | select(.body | contains($marker)) | .url][0] // ""' 2>/dev/null || printf '')"
  else
    result="$(gh issue list --state all --search "$marker in:body" --limit 20 --json url,body 2>/dev/null | jq -r --arg marker "$marker" '[.[] | select(.body | contains($marker)) | .url][0] // ""' 2>/dev/null || printf '')"
  fi
  printf '%s' "$result"
}

mark_task_synced() {
  local task="$1" url="$2" destination
  destination="$SYNCED_TASK_DIR/$(basename "$task")"
  mv "$task" "$destination"
  printf '%s\n' "$url" > "$destination.issue-url"
  chmod 600 "$destination" "$destination.issue-url" 2>/dev/null || true
  log "registro local sincronizado como Issue: $url"
}

sync_pending_tasks() {
  local task title marker output existing
  command -v gh >/dev/null 2>&1 || { warn "gh ausente; registros locais de tarefa permanecem pendentes para sincronização posterior."; return 0; }
  if command -v timeout >/dev/null 2>&1; then
    timeout "$REMOTE_TIMEOUT" gh auth status >/dev/null 2>&1 || { warn "gh sem autenticação utilizável; registros de tarefa permanecem locais."; return 0; }
  else
    gh auth status >/dev/null 2>&1 || { warn "gh sem autenticação utilizável; registros de tarefa permanecem locais."; return 0; }
  fi

  local task_list_tmp
  task_list_tmp="$(mktemp)"
  find "$PENDING_TASK_DIR" -maxdepth 1 -type f -name '*.md' -print0 | sort -z > "$task_list_tmp"

  while IFS= read -r -d '' task; do
    title="$(sed -n '1s/^# //p' "$task")"
    marker="$(sed -n 's/^- local_task_id: //p' "$task")"
    [ -n "$title" ] || { warn "registro local sem título válido: $task"; continue; }
    [ -n "$marker" ] || { warn "registro local sem local_task_id: $task"; continue; }

    existing="$(find_existing_issue "$marker")"
    if printf '%s' "$existing" | grep -E '^https?://' >/dev/null; then
      mark_task_synced "$task" "$existing"
      continue
    fi

    if command -v timeout >/dev/null 2>&1; then
      output="$(timeout "$REMOTE_TIMEOUT" gh issue create --title "$title" --body-file "$task" 2>/dev/null || true)"
    else
      output="$(gh issue create --title "$title" --body-file "$task" 2>/dev/null || true)"
    fi
    if printf '%s' "$output" | grep -E '^https?://' >/dev/null; then
      mark_task_synced "$task" "$output"
      continue
    fi

    # Se o POST tiver sido aceito mas a resposta tiver se perdido, a busca pelo
    # marcador evita criar outra Issue na próxima sincronização.
    existing="$(find_existing_issue "$marker")"
    if printf '%s' "$existing" | grep -E '^https?://' >/dev/null; then
      mark_task_synced "$task" "$existing"
    else
      warn "não foi possível confirmar Issue para $(basename "$task"); registro permanece pendente."
    fi
  done < "$task_list_tmp"
  rm -f "$task_list_tmp"
}

checkpoint() {
  assert_not_production
  local ts sha short dir list safe_list skipped size file suffix attempt
  ts="$(date -u +'%Y%m%dT%H%M%SZ')"
  sha="$(git rev-parse HEAD)"
  short="$(git rev-parse --short=12 HEAD)"

  # Evitar colisão: incluir sufixo único e tentar criação atômica.
  suffix="${BASHPID}-${RANDOM}"
  dir="$CHECKPOINT_DIR/${ts}-${short}-${suffix}"
  attempt=0
  while [ -e "$dir" ]; do
    attempt=$((attempt + 1))
    [ "$attempt" -lt 100 ] || die "não foi possível criar diretório de checkpoint único após 100 tentativas."
    suffix="${BASHPID}-${RANDOM}-${attempt}"
    dir="$CHECKPOINT_DIR/${ts}-${short}-${suffix}"
  done

  mkdir "$dir"
  chmod 700 "$dir"

  printf '%s\n' "$sha" > "$dir/base-sha.txt"
  current_branch > "$dir/branch.txt"
  printf '%s\n' "$repo_name" > "$dir/repository.txt"
  git status --porcelain=v1 --untracked-files=no > "$dir/status.txt"

  # Inicializar arquivo de skipped antes de qualquer filtragem.
  skipped="$dir/skipped-untracked.txt"
  : > "$skipped"

  # Filtrar arquivos sensíveis dos diffs rastreados/staged.
  local changed_tracked changed_staged safe_changed_list
  changed_tracked="$dir/tracked-changed.list0"
  changed_staged="$dir/staged-changed.list0"
  safe_changed_list="$dir/safe-changed.list0"
  : > "$changed_tracked"; : > "$changed_staged"; : > "$safe_changed_list"

  git diff --name-only -z HEAD > "$changed_tracked"
  git diff --cached --name-only -z > "$changed_staged"
  cat "$changed_tracked" "$changed_staged" | sort -uz > "$safe_changed_list"

  while IFS= read -r -d '' file; do
    if sensitive_path "$file"; then
      printf 'tracked-sensitive sha256=%s\n' "$(printf '%s' "$file" | sha256sum | cut -d' ' -f1)" >> "$skipped"
      # Não incluir conteúdo sensível — registrar apenas que foi filtrado.
      printf '# FILTERED: arquivo sensível %s excluído do checkpoint\n' "$file" >> "$dir/tracked-working-tree.patch"
      printf '# FILTERED: arquivo sensível %s excluído do checkpoint\n' "$file" >> "$dir/index.patch"
    else
      git diff --binary HEAD -- "$file" >> "$dir/tracked-working-tree.patch"
      git diff --cached --binary -- "$file" >> "$dir/index.patch"
    fi
  done < "$safe_changed_list"

  rm -f "$changed_tracked" "$changed_staged" "$safe_changed_list"

  list="$dir/untracked-all.list0"
  safe_list="$dir/untracked-safe.list0"
  : > "$list"; : > "$safe_list"
  git ls-files --others --exclude-standard -z > "$list"

  while IFS= read -r -d '' file; do
    if sensitive_path "$file"; then
      printf 'sensitive-path sha256=%s\n' "$(printf '%s' "$file" | sha256sum | cut -d' ' -f1)" >> "$skipped"
      continue
    fi
    if [ -L "$file" ]; then
      printf 'symlink sha256=%s\n' "$(printf '%s' "$file" | sha256sum | cut -d' ' -f1)" >> "$skipped"
      continue
    fi
    if [ -f "$file" ]; then
      size="$(wc -c < "$file" 2>/dev/null || printf '0')"
      if [ "$size" -gt "$MAX_UNTRACKED_BYTES" ]; then
        printf 'oversized sha256=%s bytes=%s\n' "$(printf '%s' "$file" | sha256sum | cut -d' ' -f1)" "$size" >> "$skipped"
        continue
      fi
      printf '%s\0' "$file" >> "$safe_list"
    fi
  done < "$list"

  if [ -s "$safe_list" ]; then
    tar --null -T "$safe_list" -czf "$dir/untracked-safe.tar.gz"
  fi

  # Bundle: verificar se histórico commitado tem arquivos sensíveis.
  # Se encontrar .env ou chaves no histórico, bloquear o bundle.
  local bundle_blocked=""
  if git log --all --name-only --format="" | grep -Eiq '(^|/)(\.env($|\.).*|[^/]*\.(pem|key|p12|pfx|jks|keystore)$)'; then
    bundle_blocked="1"
    printf 'bundle-blocked: histórico contém arquivos sensíveis; bundle não criado\n' >> "$skipped"
    warn "histórico Git contém nomes de arquivos sensíveis (.env, chaves); bundle bloqueado para proteger segredos. Checkpoint preserva apenas diffs seguros."
  fi

  if [ -z "$bundle_blocked" ]; then
    git bundle create "$dir/repository.bundle" --branches --tags >/dev/null 2>&1 || \
      git bundle create "$dir/repository.bundle" HEAD >/dev/null 2>&1
  fi

  rm -f "$list" "$safe_list"
  (
    cd "$dir"
    find . -maxdepth 1 -type f ! -name 'SHA256SUMS' -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
  )
  chmod 600 "$dir"/* 2>/dev/null || true
  printf '%s\n' "$dir" > "$STATE_DIR/last-checkpoint"
  chmod 600 "$STATE_DIR/last-checkpoint" 2>/dev/null || true

  log "checkpoint local criado: $dir"
  if [ -s "$skipped" ]; then
    warn "arquivos não rastreados sensíveis/grandes/symlinks foram excluídos; skipped-untracked.txt guarda somente motivo e hash do nome."
  fi
}

validate() {
  assert_not_production
  local mode="${1:-$CI_MODE}"
  [ -f scripts/ci-local.sh ] || die "scripts/ci-local.sh ausente."
  checkpoint
  log "executando CI local: bash scripts/ci-local.sh $mode"
  bash scripts/ci-local.sh "$mode"
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
    if [ -n "$(git status --porcelain=v1)" ]; then
      warn "working tree possui alterações não commitadas; push automático do HEAD foi recusado. O checkpoint preserva o estado local."
      sync_pending_tasks
      return 0
    fi
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
