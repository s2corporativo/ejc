#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$ROOT/scripts/ejc-local-first.sh"
[ -f "$SCRIPT" ] || { echo "script local-first ausente" >&2; exit 1; }

TMP="$(mktemp -d)"
cleanup() {
  if [ -d "$TMP" ]; then
    find "$TMP" -depth -mindepth 1 -delete 2>/dev/null || true
    rmdir "$TMP" 2>/dev/null || true
  fi
}
trap cleanup EXIT

mkdir -p "$TMP/repo/scripts"
cp "$SCRIPT" "$TMP/repo/scripts/ejc-local-first.sh"
cat > "$TMP/repo/scripts/ci-local.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf 'dummy-ci mode=%s\n' "${1:-full}"
EOF
# Deliberadamente sem chmod: validate deve chamar o CI por `bash`.

cd "$TMP/repo"
git init -q
git config user.email test@example.invalid
git config user.name test
echo base > tracked.txt
git add tracked.txt scripts
git commit -qm init
git switch -qc feat/test-fallback

echo changed >> tracked.txt
echo safe > novo.txt
echo secret > .env.local

ENV_COMMON=(
  EJC_PRODUCTION_DIR=/definitely/not/here
  EJC_RECOVERY_ROOT="$TMP/recovery"
  EJC_GIT_TIMEOUT=1
)

env "${ENV_COMMON[@]}" bash scripts/ejc-local-first.sh register \
  "Fallback técnico" "Validar continuidade local sem GitHub e sem dado real."
TASK="$(cat "$TMP/recovery/repo/last-task")"
test -f "$TASK"
grep -q '^# Fallback técnico$' "$TASK"
grep -q '^\- local_task_id: ' "$TASK"
grep -q '^\- sincronizacao: pendente$' "$TASK"

if env "${ENV_COMMON[@]}" bash scripts/ejc-local-first.sh register \
  "Segredo proibido" "api_key=valor-nao-deve-ser-registrado" >/dev/null 2>&1; then
  echo "registro com aparência de segredo deveria ter sido bloqueado" >&2
  exit 1
fi
if env "${ENV_COMMON[@]}" bash scripts/ejc-local-first.sh register \
  "PII proibida" "Contato cliente@example.com" >/dev/null 2>&1; then
  echo "registro com PII óbvia deveria ter sido bloqueado" >&2
  exit 1
fi

env "${ENV_COMMON[@]}" bash scripts/ejc-local-first.sh checkpoint
CP="$(cat "$TMP/recovery/repo/last-checkpoint")"
test -f "$CP/tracked-working-tree.patch"
test -f "$CP/untracked-safe.tar.gz"
test -f "$CP/repository.bundle"
test -f "$CP/SHA256SUMS"
test -f "$CP/repository.txt"
test ! -e "$CP/source-root.txt"
if grep -q '.env.local' "$CP/status.txt"; then
  echo "status do checkpoint não deve guardar nome de untracked sensível" >&2
  exit 1
fi
grep -q '^sensitive-path sha256=' "$CP/skipped-untracked.txt"
if grep -q '.env.local' "$CP/skipped-untracked.txt"; then
  echo "nome sensível bruto não pode ficar no metadata do checkpoint" >&2
  exit 1
fi
ARCHIVE_LIST="$TMP/untracked-safe.list"
tar -tzf "$CP/untracked-safe.tar.gz" > "$ARCHIVE_LIST"
grep -q '^novo.txt$' "$ARCHIVE_LIST"
if grep -q '.env.local' "$ARCHIVE_LIST"; then
  echo ".env.local não pode entrar no snapshot" >&2
  exit 1
fi

# Achado 3a: .env rastreado incluído em diff staged não deve vazar conteúdo sensível.
echo "SECRET_KEY=should-not-leak" > .env
git add .env
env "${ENV_COMMON[@]}" bash scripts/ejc-local-first.sh checkpoint
CP_TRACKED="$(cat "$TMP/recovery/repo/last-checkpoint")"
if grep -q 'SECRET_KEY=should-not-leak' "$CP_TRACKED/index.patch"; then
  echo "segredo de .env rastreado vazou no checkpoint (index.patch)" >&2
  exit 1
fi
grep -q 'tracked-sensitive sha256=' "$CP_TRACKED/skipped-untracked.txt"

# Achado 3b: segredo já commitado no histórico deve bloquear bundle.
git commit -qm 'INSEGURO: commitar .env com segredo (só para teste)'
env "${ENV_COMMON[@]}" bash scripts/ejc-local-first.sh checkpoint
CP_HISTORY="$(cat "$TMP/recovery/repo/last-checkpoint")"
if [ -f "$CP_HISTORY/repository.bundle" ]; then
  echo "bundle não deveria ter sido criado quando histórico tem .env" >&2
  exit 1
fi
grep -q 'bundle-blocked' "$CP_HISTORY/skipped-untracked.txt"

VALIDATE_OUTPUT="$(env "${ENV_COMMON[@]}" bash scripts/ejc-local-first.sh validate fast)"
grep -q 'dummy-ci mode=fast' <<< "$VALIDATE_OUTPUT"

# Remoto local saudável + gh falso: simula POST aceito com resposta perdida.
git init --bare -q "$TMP/remote.git"
git remote add origin "$TMP/remote.git"
git push -q -u origin feat/test-fallback
git --git-dir="$TMP/remote.git" symbolic-ref HEAD refs/heads/feat/test-fallback
mkdir -p "$TMP/bin" "$TMP/gh-state"
cat > "$TMP/bin/gh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
STATE="${GH_FAKE_STATE:?}"
if [ "${1:-}" = "auth" ] && [ "${2:-}" = "status" ]; then
  exit 0
fi
if [ "${1:-}" = "issue" ] && [ "${2:-}" = "list" ]; then
  if [ -f "$STATE/created" ]; then
    marker=""
    prev=""
    for arg in "$@"; do
      if [ "$prev" = "--search" ]; then
        marker="${arg% in:body}"
      fi
      prev="$arg"
    done
    printf '[{"url":"https://example.invalid/issues/1","body":"%s"}]\n' "$marker"
  else
    printf '[]\n'
  fi
  exit 0
fi
if [ "${1:-}" = "issue" ] && [ "${2:-}" = "create" ]; then
  printf '1\n' >> "$STATE/create-count"
  touch "$STATE/created"
  # Simula criação remota bem-sucedida, mas perda/timeout da resposta local.
  exit 124
fi
exit 2
EOF
chmod +x "$TMP/bin/gh"

SYNC_ENV=(
  "${ENV_COMMON[@]}"
  EJC_LOCAL_FIRST_AUTO_PUSH=0
  PATH="$TMP/bin:$PATH"
  GH_FAKE_STATE="$TMP/gh-state"
)
env "${SYNC_ENV[@]}" bash scripts/ejc-local-first.sh sync >/dev/null
SYNCED_TASK="$TMP/recovery/repo/synced-tasks/$(basename "$TASK")"
test -f "$SYNCED_TASK"
test -f "$SYNCED_TASK.issue-url"
test "$(wc -l < "$TMP/gh-state/create-count" | tr -d ' ')" = "1"

# Recoloca o mesmo registro como pendente: busca por local_task_id deve encontrá-lo
# antes de novo POST, mantendo exatamente uma criação.
cp "$SYNCED_TASK" "$TMP/recovery/repo/pending-tasks/$(basename "$TASK")"
env "${SYNC_ENV[@]}" bash scripts/ejc-local-first.sh sync >/dev/null
test "$(wc -l < "$TMP/gh-state/create-count" | tr -d ' ')" = "1"

# Branch local avança, mas working tree fica sujo: push automático deve ser recusado.
echo ahead > ahead.txt
git add ahead.txt
git commit -qm 'test: commit local à frente'
echo dirty >> tracked.txt
LOCAL_HEAD="$(git rev-parse HEAD)"
REMOTE_HEAD_BEFORE="$(git --git-dir="$TMP/remote.git" rev-parse refs/heads/feat/test-fallback)"
test "$LOCAL_HEAD" != "$REMOTE_HEAD_BEFORE"
DIRTY_SYNC_ENV=(
  "${ENV_COMMON[@]}"
  EJC_LOCAL_FIRST_AUTO_PUSH=1
  PATH="$TMP/bin:$PATH"
  GH_FAKE_STATE="$TMP/gh-state"
)
env "${DIRTY_SYNC_ENV[@]}" bash scripts/ejc-local-first.sh sync >/dev/null
REMOTE_HEAD_AFTER="$(git --git-dir="$TMP/remote.git" rev-parse refs/heads/feat/test-fallback)"
test "$REMOTE_HEAD_AFTER" = "$REMOTE_HEAD_BEFORE"

# Nova tarefa + remoto DNS inválido: deve permanecer local e marcar modo offline.
env "${ENV_COMMON[@]}" bash scripts/ejc-local-first.sh register \
  "Fallback offline" "Preservar tarefa quando o remoto não responder."
OFFLINE_TASK="$(cat "$TMP/recovery/repo/last-task")"
git remote set-url origin https://invalid.invalid/ejc.git

# Achado 7: desabilitar prompts de credencial git durante testes offline.
export GIT_TERMINAL_PROMPT=0

env "${ENV_COMMON[@]}" GIT_TERMINAL_PROMPT=0 bash scripts/ejc-local-first.sh status >/dev/null 2>&1
grep -q '^offline$' "$TMP/recovery/repo/mode"
env "${ENV_COMMON[@]}" GIT_TERMINAL_PROMPT=0 bash scripts/ejc-local-first.sh sync >/dev/null 2>&1
grep -q '^offline$' "$TMP/recovery/repo/mode"
test -f "$OFFLINE_TASK"

unset GIT_TERMINAL_PROMPT

# Nem uma variável legada de override pode liberar o checkout definido como produção.
if env EJC_PRODUCTION_DIR="$TMP/repo" EJC_ALLOW_PRODUCTION_WORKTREE=1 \
  EJC_RECOVERY_ROOT="$TMP/recovery-prod" bash scripts/ejc-local-first.sh checkpoint >/dev/null 2>&1; then
  echo "checkpoint deveria ter sido bloqueado no diretório de produção" >&2
  exit 1
fi

echo "test_ejc_local_first: OK"
