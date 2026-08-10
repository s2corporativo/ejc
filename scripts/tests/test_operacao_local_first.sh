#!/usr/bin/env bash
set -euo pipefail

SCRIPT="${1:-scripts/operacao-local-first.sh}"
[ -f "$SCRIPT" ] || { echo "script ausente: $SCRIPT" >&2; exit 1; }

TMP="$(mktemp -d)"
safe_cleanup() {
  if [ -d "$TMP" ]; then
    find "$TMP" -depth -mindepth 1 -delete
    rmdir "$TMP"
  fi
}
trap safe_cleanup EXIT

ROOT="$TMP/ejc"
SNAPS="$TMP/snaps"
WORK="$TMP/worktrees"
PROD="$TMP/producao"
mkdir -p "$ROOT"/{backend,frontend,scripts,nginx,uploads,data,docs,config}
mkdir -p "$PROD"
printf 'print("ok")\n' > "$ROOT/backend/a.py"
printf 'export const x = 1\n' > "$ROOT/frontend/a.ts"
printf 'services: {}\n' > "$ROOT/docker-compose.yml"
printf 'documentacao\n' > "$ROOT/docs/a.md"
printf '{}\n' > "$ROOT/config/a.json"
printf 'SEGREDO_NAO_DEVE_ENTRAR\n' > "$ROOT/.env"
printf 'cliente\n' > "$ROOT/uploads/cliente.txt"
printf 'db\n' > "$ROOT/data/db.txt"

cat > "$ROOT/scripts/ci-local.sh" <<'CI'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$1" > "${EJC_TEST_CI_MARKER:?}"
CI
chmod +x "$ROOT/scripts/ci-local.sh"

# Repositório local fictício: o teste não precisa de rede nem GitHub.
git -C "$ROOT" init -q
git -C "$ROOT" config user.email teste@local.invalid
git -C "$ROOT" config user.name "EJC Teste"
git -C "$ROOT" add backend frontend scripts nginx docs config docker-compose.yml
git -C "$ROOT" commit -qm inicial
git -C "$ROOT" switch -c trabalho >/dev/null 2>&1

COMMON=(
  EJC_ROOT="$ROOT"
  EJC_WORK_ROOT="$WORK"
  EJC_SNAPSHOT_ROOT="$SNAPS"
  EJC_PROD_ROOT="$PROD"
)

STATUS="$(env "${COMMON[@]}" bash "$SCRIPT" status)"
grep -q '^github_required_for_work=false$' <<<"$STATUS"
grep -q '^workspace_safe=true$' <<<"$STATUS"
SOURCE_ID="$(sed -n 's/^source_id=//p' <<<"$STATUS")"
[[ "$SOURCE_ID" =~ ^[0-9a-f]{40}$ ]]

# Untracked NÃO faz parte do checkpoint Git: não altera a identidade nem entra no tar.
printf 'nao versionado\n' > "$ROOT/backend/untracked.py"
STATUS_UNTRACKED="$(env "${COMMON[@]}" bash "$SCRIPT" status)"
UNTRACKED_ID="$(sed -n 's/^source_id=//p' <<<"$STATUS_UNTRACKED")"
[ "$UNTRACKED_ID" = "$SOURCE_ID" ]

# Alteração tracked sem commit muda a identidade para fingerprint local.
printf 'alterado\n' >> "$ROOT/docs/a.md"
STATUS_DIRTY="$(env "${COMMON[@]}" bash "$SCRIPT" status)"
DIRTY_ID="$(sed -n 's/^source_id=//p' <<<"$STATUS_DIRTY")"
[[ "$DIRTY_ID" == local-* ]]
git -C "$ROOT" checkout -- docs/a.md

SNAP_DIR_1="$(env "${COMMON[@]}" bash "$SCRIPT" checkpoint | tail -1)"
SNAP_DIR_2="$(env "${COMMON[@]}" bash "$SCRIPT" checkpoint | tail -1)"
[ "$SNAP_DIR_1" != "$SNAP_DIR_2" ]
for SNAP_DIR in "$SNAP_DIR_1" "$SNAP_DIR_2"; do
  [ -f "$SNAP_DIR/source.tar.gz" ]
  [ -f "$SNAP_DIR/source.tar.gz.sha256" ]
  [ "$(cat "$SNAP_DIR/source_id.txt")" = "$SOURCE_ID" ]
  if tar -tzf "$SNAP_DIR/source.tar.gz" | grep -Eq '(^|/)\.env$|(^|/)uploads/|(^|/)data/|backend/untracked\.py$'; then
    echo "checkpoint incluiu segredo/dados/untracked" >&2
    exit 1
  fi
done

CI_MARK="$TMP/ci-mode.txt"
EJC_TEST_CI_MARKER="$CI_MARK" env "${COMMON[@]}" EJC_CI_MODE=fast \
  bash "$SCRIPT" validate >/dev/null
[ "$(cat "$CI_MARK")" = "fast" ]

# Worktree é criado fora da raiz produtiva e sem acesso remoto.
PREP="$(env "${COMMON[@]}" bash "$SCRIPT" prepare teste-local | tail -1)"
[ -d "$PREP" ]
[[ "$PREP" == "$WORK/"* ]]

# Produção nunca é aceita como workspace, nem para validate/checkpoint.
if EJC_ROOT="$PROD" EJC_PROD_ROOT="$PROD" bash "$SCRIPT" checkpoint >/dev/null 2>&1; then
  echo "checkpoint aceitou diretório produtivo" >&2
  exit 1
fi
if EJC_TEST_CI_MARKER="$CI_MARK" EJC_ROOT="$PROD" EJC_PROD_ROOT="$PROD" \
  bash "$SCRIPT" validate >/dev/null 2>&1; then
  echo "validate aceitou diretório produtivo" >&2
  exit 1
fi

# Remote indisponível é TEMPFAIL (75), preservando a branch e sem force/rewrite.
git -C "$ROOT" remote add origin "$TMP/remoto-inexistente.git"
set +e
env "${COMMON[@]}" bash "$SCRIPT" sync >/dev/null 2>&1
SYNC_RC=$?
set -e
[ "$SYNC_RC" -eq 75 ] || { echo "sync offline deveria retornar 75, retornou $SYNC_RC" >&2; exit 1; }
[ "$(git -C "$ROOT" branch --show-current)" = "trabalho" ]

# O wrapper não contém caminho de deploy paralelo nem operações Git destrutivas.
! grep -qE 'git push .*--force|git reset --hard|git clean -fd' "$SCRIPT"
! grep -qE '^[[:space:]]*deploy\)' "$SCRIPT"

echo "test_operacao_local_first: OK"
