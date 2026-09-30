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

# ── Modo PostgreSQL local via docker exec ───────────────────────────────────
mkdir -p "$TMP/pgbin"
cat > "$TMP/pgbin/docker" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  inspect)
    [ "${2:-}" = "woodpecker-test-db" ]
    ;;
  exec)
    args="$*"
    if grep -Fq "__GOOD_SHA__" <<<"$args"; then
      printf '%s\n' '88|654321'
    fi
    ;;
  *)
    echo "docker inesperado: $*" >&2
    exit 2
    ;;
esac
EOF
sed -i "s/__GOOD_SHA__/$GOOD_SHA/g" "$TMP/pgbin/docker"
chmod 755 "$TMP/pgbin/docker"

cat > "$TMP/woodpecker-pg.env" <<EOF
WOODPECKER_LOCAL_PG_CONTAINER=woodpecker-test-db
WOODPECKER_LOCAL_DB=
WOODPECKER_SERVER_URL=https://ci.example.invalid
WOODPECKER_TOKEN=TROCAR
EOF
chmod 600 "$TMP/woodpecker-pg.env"

PATH="$TMP/pgbin:$PATH" \
WOODPECKER_HOST_ENV_FILE="$TMP/woodpecker-pg.env" \
  "$ROOT/woodpecker-approved-sha.sh" s2corporativo/test "$GOOD_SHA" \
  | grep -q 'APROVADO modo=postgres'

if PATH="$TMP/pgbin:$PATH" \
   WOODPECKER_HOST_ENV_FILE="$TMP/woodpecker-pg.env" \
   "$ROOT/woodpecker-approved-sha.sh" s2corporativo/test "$BAD_SHA" >/dev/null 2>&1; then
  echo "gate PostgreSQL aceitou SHA sem pipeline aprovado" >&2
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


# ── Upgrade do instalador: env legado SEM WOODPECKER_LOCAL_DB ───────────────
# Regressão do rollout real: instalações anteriores tinham apenas URL/token.
UPGRADE="$TMP/upgrade"
mkdir -p "$UPGRADE/etc" "$UPGRADE/host"
HEAD_SHA="$(git -C "$ROOT/../.." rev-parse HEAD)"
python3 - "$UPGRADE/woodpecker.sqlite" "$HEAD_SHA" <<'PY'
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
  "commit" TEXT NOT NULL,
  branch TEXT NOT NULL,
  event TEXT NOT NULL,
  status TEXT NOT NULL,
  finished INTEGER NOT NULL
);
""")
con.execute("INSERT INTO repos(id, full_name) VALUES(?, ?)", (2, "s2corporativo/ejc"))
con.execute(
    "INSERT INTO pipelines(repo_id, number, \"commit\", branch, event, status, finished) VALUES(?,?,?,?,?,?,?)",
    (2, 901, sha, "main", "push", "success", 999999),
)
con.commit()
con.close()
PY
cat > "$UPGRADE/etc/woodpecker.env" <<'EOF'
WOODPECKER_SERVER_URL=https://ci.example.invalid
WOODPECKER_TOKEN=TROCAR
EOF
chmod 600 "$UPGRADE/etc/woodpecker.env"

EJC_HOST_AUTOMATION_TARGET="$UPGRADE/host" \
EJC_HOST_AUTOMATION_ENV_DIR="$UPGRADE/etc" \
WOODPECKER_LOCAL_PG_CONTAINER_DEFAULT=woodpecker-does-not-exist \
WOODPECKER_LOCAL_DB_DEFAULT="$UPGRADE/woodpecker.sqlite" \
  "$ROOT/install.sh" >/dev/null

grep -Fxq "WOODPECKER_LOCAL_DB=$UPGRADE/woodpecker.sqlite" \
  "$UPGRADE/etc/woodpecker.env" || {
    echo "install.sh não migrou env legado sem WOODPECKER_LOCAL_DB" >&2
    exit 1
  }
[ "$(grep -c '^WOODPECKER_LOCAL_DB=' "$UPGRADE/etc/woodpecker.env")" -eq 1 ] || {
  echo "install.sh duplicou WOODPECKER_LOCAL_DB no upgrade" >&2
  exit 1
}

echo "upgrade de woodpecker.env legado: SQLite local configurado"


echo "gate Woodpecker: API, PostgreSQL local e SQLite legado aprovam/bloqueiam conforme esperado"

# Regressao: fetch explicito deve atualizar origin/main, nao apenas FETCH_HEAD.
for rel in ejc-deploy-approved.sh install-ejc-deploy.sh ../../scripts/deploy_manual.sh; do
  file="$ROOT/$rel"
  grep -Fq "refs/heads/main:refs/remotes/origin/main" "$file" || {
    echo "$rel nao atualiza origin/main explicitamente" >&2
    exit 1
  }
  if grep -Fq "fetch --prune origin main" "$file"; then
    echo "$rel voltou ao fetch ambiguo" >&2
    exit 1
  fi
done
