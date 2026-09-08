#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"

GOOD_SHA="1111111111111111111111111111111111111111"
BAD_SHA="2222222222222222222222222222222222222222"

# ── Modo API ────────────────────────────────────────────────────────────────
cat > "$TMP/woodpecker.env" <<'EOF'
WOODPECKER_SERVER_URL=https://ci.example.invalid
WOODPECKER_TOKEN=test-token-not-secret
WOODPECKER_LOCAL_DB=
EOF
chmod 600 "$TMP/woodpecker.env"

cat > "$TMP/bin/curl" <<EOF
#!/usr/bin/env bash
set -euo pipefail
url="\${!#}"
case "\$url" in
  */api/repos/lookup/s2corporativo/test)
    printf '%s\n' '{"id":7}'
    ;;
  */api/repos/7/pipelines*)
    printf '%s\n' '[{"number":42,"commit":"$GOOD_SHA","branch":"main","event":"push","status":"success","finished":123456}]'
    ;;
  *)
    echo "URL inesperada: \$url" >&2
    exit 22
    ;;
esac
EOF
chmod 755 "$TMP/bin/curl"

PATH="$TMP/bin:$PATH" \
WOODPECKER_HOST_ENV_FILE="$TMP/woodpecker.env" \
  "$ROOT/woodpecker-approved-sha.sh" s2corporativo/test "$GOOD_SHA" \
  | grep -q 'APROVADO modo=api'

if PATH="$TMP/bin:$PATH" \
   WOODPECKER_HOST_ENV_FILE="$TMP/woodpecker.env" \
   "$ROOT/woodpecker-approved-sha.sh" s2corporativo/test "$BAD_SHA" >/dev/null 2>&1; then
  echo "gate API aceitou SHA sem pipeline aprovado" >&2
  exit 1
fi

# ── Modo SQLite local read-only ─────────────────────────────────────────────
python3 - "$TMP/woodpecker.sqlite" "$GOOD_SHA" <<'PY'
import sqlite3
import sys

path, sha = sys.argv[1], sys.argv[2]
con = sqlite3.connect(path)
con.executescript("""
CREATE TABLE repos (id INTEGER PRIMARY KEY, full_name TEXT NOT NULL);
CREATE TABLE pipelines (
  id INTEGER PRIMARY KEY,
  repo_id INTEGER NOT NULL,
  number INTEGER NOT NULL,
  \"commit\" TEXT NOT NULL,
  branch TEXT NOT NULL,
  event TEXT NOT NULL,
  status TEXT NOT NULL,
  finished INTEGER NOT NULL
);
""")
con.execute("INSERT INTO repos(id, full_name) VALUES(?, ?)", (7, "s2corporativo/test"))
con.execute(
    "INSERT INTO pipelines(repo_id, number, \"commit\", branch, event, status, finished) VALUES(?,?,?,?,?,?,?)",
    (7, 77, sha, "main", "push", "success", 654321),
)
con.commit()
con.close()
PY

cat > "$TMP/woodpecker-local.env" <<EOF
WOODPECKER_LOCAL_DB=$TMP/woodpecker.sqlite
WOODPECKER_SERVER_URL=https://ci.example.invalid
WOODPECKER_TOKEN=TROCAR
EOF
chmod 600 "$TMP/woodpecker-local.env"

WOODPECKER_HOST_ENV_FILE="$TMP/woodpecker-local.env" \
  "$ROOT/woodpecker-approved-sha.sh" s2corporativo/test "$GOOD_SHA" \
  | grep -q 'APROVADO modo=sqlite'

if WOODPECKER_HOST_ENV_FILE="$TMP/woodpecker-local.env" \
   "$ROOT/woodpecker-approved-sha.sh" s2corporativo/test "$BAD_SHA" >/dev/null 2>&1; then
  echo "gate SQLite aceitou SHA sem pipeline aprovado" >&2
  exit 1
fi

# Symlink de DB é recusado mesmo que a origem seja SQLite válida.
ln -s "$TMP/woodpecker.sqlite" "$TMP/woodpecker-link.sqlite"
cat > "$TMP/woodpecker-link.env" <<EOF
WOODPECKER_LOCAL_DB=$TMP/woodpecker-link.sqlite
WOODPECKER_TOKEN=TROCAR
EOF
chmod 600 "$TMP/woodpecker-link.env"
if WOODPECKER_HOST_ENV_FILE="$TMP/woodpecker-link.env" \
   "$ROOT/woodpecker-approved-sha.sh" s2corporativo/test "$GOOD_SHA" >/dev/null 2>&1; then
  echo "gate SQLite aceitou DB via symlink" >&2
  exit 1
fi

echo "gate Woodpecker: API e SQLite local aprovam/bloqueiam conforme esperado"
