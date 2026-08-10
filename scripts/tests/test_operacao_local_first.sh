#!/usr/bin/env bash
set -euo pipefail

SCRIPT="${1:-scripts/operacao-local-first.sh}"
[ -f "$SCRIPT" ] || { echo "script ausente: $SCRIPT" >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
ROOT="$TMP/ejc"
SNAPS="$TMP/snaps"
mkdir -p "$ROOT"/{backend,frontend,scripts,nginx,uploads,data}
printf 'print("ok")\n' > "$ROOT/backend/a.py"
printf 'export const x = 1\n' > "$ROOT/frontend/a.ts"
printf 'services: {}\n' > "$ROOT/docker-compose.yml"
printf 'SEGREDO_NAO_DEVE_ENTRAR\n' > "$ROOT/.env"
printf 'cliente\n' > "$ROOT/uploads/cliente.txt"
printf 'db\n' > "$ROOT/data/db.txt"

cat > "$ROOT/scripts/ci-local.sh" <<'CI'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$1" > "${EJC_TEST_CI_MARKER:?}"
CI
chmod +x "$ROOT/scripts/ci-local.sh"

cat > "$ROOT/scripts/backup.sh" <<'BK'
#!/usr/bin/env bash
exit 0
BK
chmod +x "$ROOT/scripts/backup.sh"

cat > "$ROOT/scripts/deploy_vps_safe.sh" <<'DEP'
#!/usr/bin/env bash
set -euo pipefail
{
  printf 'TARGET_SHA=%s\n' "${TARGET_SHA:-}"
  printf 'APP_DIR=%s\n' "${APP_DIR:-}"
  printf 'REQUIRE_PREDEPLOY_BACKUP=%s\n' "${REQUIRE_PREDEPLOY_BACKUP:-}"
} > "${EJC_TEST_DEPLOY_MARKER:?}"
DEP
chmod +x "$ROOT/scripts/deploy_vps_safe.sh"

STATUS="$(EJC_ROOT="$ROOT" EJC_SNAPSHOT_ROOT="$SNAPS" bash "$SCRIPT" status)"
grep -q '^github_required=false$' <<<"$STATUS"
SOURCE_ID="$(sed -n 's/^source_id=//p' <<<"$STATUS")"
[[ "$SOURCE_ID" == local-* ]]

SNAP_DIR="$(EJC_ROOT="$ROOT" EJC_SNAPSHOT_ROOT="$SNAPS" bash "$SCRIPT" snapshot | tail -1)"
[ -f "$SNAP_DIR/source.tar.gz" ]
[ -f "$SNAP_DIR/source.tar.gz.sha256" ]
[ "$(cat "$SNAP_DIR/source_id.txt")" = "$SOURCE_ID" ]
if tar -tzf "$SNAP_DIR/source.tar.gz" | grep -Eq '(^|/)\.env$|(^|/)uploads/|(^|/)data/'; then
  echo "snapshot incluiu segredo/dados" >&2
  exit 1
fi

CI_MARK="$TMP/ci-mode.txt"
EJC_TEST_CI_MARKER="$CI_MARK" EJC_ROOT="$ROOT" EJC_SNAPSHOT_ROOT="$SNAPS" EJC_CI_MODE=fast \
  bash "$SCRIPT" validate >/dev/null
[ "$(cat "$CI_MARK")" = "fast" ]

DEPLOY_MARK="$TMP/deploy-env.txt"
EJC_TEST_CI_MARKER="$CI_MARK" EJC_TEST_DEPLOY_MARKER="$DEPLOY_MARK" \
EJC_ROOT="$ROOT" EJC_SNAPSHOT_ROOT="$SNAPS" EJC_CI_MODE=fast \
  bash "$SCRIPT" deploy >/dev/null

grep -q '^TARGET_SHA=local-' "$DEPLOY_MARK"
grep -q "^APP_DIR=$ROOT$" "$DEPLOY_MARK"
grep -q '^REQUIRE_PREDEPLOY_BACKUP=1$' "$DEPLOY_MARK"

echo "test_operacao_local_first: OK"
