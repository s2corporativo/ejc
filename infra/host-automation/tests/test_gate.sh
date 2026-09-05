#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"

GOOD_SHA="1111111111111111111111111111111111111111"
BAD_SHA="2222222222222222222222222222222222222222"

cat > "$TMP/woodpecker.env" <<'EOF'
WOODPECKER_SERVER_URL=https://ci.example.invalid
WOODPECKER_TOKEN=test-token-not-secret
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
  | grep -q 'APROVADO'

if PATH="$TMP/bin:$PATH" \
   WOODPECKER_HOST_ENV_FILE="$TMP/woodpecker.env" \
   "$ROOT/woodpecker-approved-sha.sh" s2corporativo/test "$BAD_SHA" >/dev/null 2>&1; then
  echo "gate aceitou SHA sem pipeline aprovado" >&2
  exit 1
fi

echo "gate Woodpecker: aprovado/bloqueado conforme esperado"
