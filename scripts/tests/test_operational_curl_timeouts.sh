#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FILES=(
  scripts/deploy_vps_safe.sh
  scripts/backup/ativar_backup.sh
  scripts/smoke_staging.sh
  infra/host-automation/ejc-deploy-approved.sh
)

python3 - "$ROOT" "${FILES[@]}" <<"PY"
from pathlib import Path
import sys

root = Path(sys.argv[1])
errors = []
checked = 0
for rel in sys.argv[2:]:
    text = (root / rel).read_text(encoding="utf-8")
    logical = []
    buf = ""
    start = 0
    for lineno, line in enumerate(text.splitlines(), 1):
        if not buf:
            start = lineno
        buf += line + "\n"
        if line.rstrip().endswith("\\"):
            continue
        logical.append((start, buf))
        buf = ""
    if buf:
        logical.append((start, buf))
    for lineno, command in logical:
        stripped = command.lstrip()
        if stripped.startswith("#") or "curl " not in command:
            continue
        checked += 1
        if "--connect-timeout" not in command or "--max-time" not in command:
            errors.append(f"{rel}:{lineno}: curl operacional sem connect/max timeout")

if errors:
    raise SystemExit("\n".join(errors))
if checked < 10:
    raise SystemExit(f"cobertura inesperadamente baixa: apenas {checked} comandos curl")
print(f"curl timeout contract: {checked} comandos ativos cobertos")
PY

TMP="$(mktemp -d)"
trap "rm -rf \"$TMP\"" EXIT
PORT_FILE="$TMP/port"
python3 - "$PORT_FILE" <<"PY" &
import socket, sys, time
path = sys.argv[1]
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", 0))
s.listen(1)
with open(path, "w", encoding="ascii") as f:
    f.write(str(s.getsockname()[1]))
conn, _ = s.accept()
with conn:
    time.sleep(10)
PY
SERVER_PID=$!
for _ in $(seq 1 50); do
  [ -s "$PORT_FILE" ] && break
  sleep 0.05
done
[ -s "$PORT_FILE" ] || { echo "servidor de teste não iniciou" >&2; kill "$SERVER_PID" 2>/dev/null || true; exit 1; }
PORT="$(cat "$PORT_FILE")"
START="$(date +%s)"
set +e
curl -fsS --connect-timeout 1 --max-time 1 "http://127.0.0.1:${PORT}/" >/dev/null 2>&1
RC=$?
set -e
ELAPSED=$(( $(date +%s) - START ))
kill "$SERVER_PID" 2>/dev/null || true
wait "$SERVER_PID" 2>/dev/null || true
[ "$RC" -ne 0 ] || { echo "curl deveria falhar por max-time" >&2; exit 1; }
[ "$ELAPSED" -le 3 ] || { echo "curl excedeu teto esperado: ${ELAPSED}s" >&2; exit 1; }
printf "curl fail-closed: conexão aceita sem resposta abortada em %ss (rc=%s)\n" "$ELAPSED" "$RC"
