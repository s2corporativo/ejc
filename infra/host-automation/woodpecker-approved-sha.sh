#!/usr/bin/env bash
set -euo pipefail

REPO_FULL_NAME="${1:-}"
TARGET_SHA="${2:-}"
ENV_FILE="${WOODPECKER_HOST_ENV_FILE:-/etc/s2-automation/woodpecker.env}"

fail() { printf '[woodpecker-gate] ERRO: %s\n' "$*" >&2; exit 2; }

[[ "$REPO_FULL_NAME" =~ ^s2corporativo/[A-Za-z0-9._-]+$ ]] || fail "repositorio fora do escopo s2corporativo"
[[ "$TARGET_SHA" =~ ^[0-9a-fA-F]{40}$ ]] || fail "SHA alvo invalido"
[ -f "$ENV_FILE" ] || fail "credencial Woodpecker ausente: $ENV_FILE"
[ "$(stat -c '%u' "$ENV_FILE")" = "0" ] || fail "$ENV_FILE deve pertencer a root"
case "$(stat -c '%a' "$ENV_FILE")" in
  600|640) ;;
  *) fail "$ENV_FILE deve usar modo 600 ou 640" ;;
esac

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

WOODPECKER_SERVER_URL="${WOODPECKER_SERVER_URL:-https://ci.depaulateixeira.adv.br}"
[ -n "${WOODPECKER_TOKEN:-}" ] || fail "WOODPECKER_TOKEN vazio"
[ "$WOODPECKER_TOKEN" != "TROCAR" ] || fail "WOODPECKER_TOKEN ainda e placeholder"

command -v curl >/dev/null 2>&1 || fail "curl ausente"
command -v python3 >/dev/null 2>&1 || fail "python3 ausente"

api="${WOODPECKER_SERVER_URL%/}/api"
auth=( -H "Authorization: Bearer ${WOODPECKER_TOKEN}" -H 'Accept: application/json' )

lookup="$(curl --fail --silent --show-error --connect-timeout 10 --max-time 30 \
  "${auth[@]}" "$api/repos/lookup/$REPO_FULL_NAME")" || fail "falha ao consultar repositorio no Woodpecker"

repo_id="$(printf '%s' "$lookup" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("id", ""))')"
[[ "$repo_id" =~ ^[0-9]+$ ]] || fail "Woodpecker nao retornou repo_id valido"

pipelines="$(curl --fail --silent --show-error --connect-timeout 10 --max-time 30 \
  "${auth[@]}" \
  "$api/repos/$repo_id/pipelines?branch=main&event=push&status=success&perPage=50")" \
  || fail "falha ao consultar pipelines aprovados"

approval="$(printf '%s' "$pipelines" | python3 - "$TARGET_SHA" <<'PY'
import json, sys
sha = sys.argv[1].lower()
try:
    rows = json.load(sys.stdin)
except Exception:
    raise SystemExit(2)
if not isinstance(rows, list):
    raise SystemExit(2)
matches = [p for p in rows if str(p.get('commit', '')).lower() == sha
           and p.get('branch') == 'main'
           and p.get('event') == 'push'
           and p.get('status') == 'success']
if not matches:
    raise SystemExit(1)
p = sorted(matches, key=lambda x: (x.get('finished', 0), x.get('number', 0)), reverse=True)[0]
print(f"{p.get('number','')}|{p.get('finished','')}")
PY
)" || rc=$?
rc="${rc:-0}"
case "$rc" in
  0) ;;
  1) fail "SHA $TARGET_SHA nao possui pipeline push/main com status success" ;;
  *) fail "resposta de pipelines invalida" ;;
esac

pipeline_number="${approval%%|*}"
[[ "$pipeline_number" =~ ^[0-9]+$ ]] || fail "pipeline aprovado sem numero valido"
printf '[woodpecker-gate] APROVADO repo=%s sha=%s pipeline=%s\n' \
  "$REPO_FULL_NAME" "$TARGET_SHA" "$pipeline_number"
