#!/usr/bin/env bash
set -Eeuo pipefail

EXPECTED_SHA="${1:?uso: post_release_hygiene.sh <sha>}"
APP_DIR="${APP_DIR:-/opt/ejc}"
REPORT_DIR="${EJC_MAINT_REPORT_DIR:-/var/lib/ejc-maintenance}"
mkdir -p "$REPORT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
MANIFEST="$REPORT_DIR/branches-post-release-${STAMP}.csv"
REPORT="$REPORT_DIR/post-release-hygiene-${STAMP}.json"
BRANCH_LOG="$REPORT_DIR/post-release-branches-${STAMP}.log"

cd "$APP_DIR"

# Segurança: higiene só roda sobre a release que acabou de ser provada.
python3 scripts/check_release_identity.py \
  --expected "$EXPECTED_SHA" \
  --app-dir "$APP_DIR"

before_kb="$(df -Pk / | awk 'NR==2 {print $3}')"
branch_rc=0
python3 scripts/branch_hygiene.py --manifest "$MANIFEST" --apply \
  >"$BRANCH_LOG" 2>&1 || branch_rc=$?

# Somente recursos descartáveis. Volumes e imagens recentes/rollback não entram.
git worktree prune
docker container prune -f --filter until=168h >/dev/null
docker builder prune -af --filter until=168h >/dev/null
docker image prune -f --filter until=168h >/dev/null

graph_rc=0
if command -v graphify >/dev/null 2>&1; then
  GRAPHIFY_MAX_WORKERS=1 graphify update "$APP_DIR" --force --no-cluster \
    >"$REPORT_DIR/graphify-post-release-${STAMP}.log" 2>&1 || graph_rc=$?
fi

after_kb="$(df -Pk / | awk 'NR==2 {print $3}')"

python3 - "$EXPECTED_SHA" "$REPORT" "$MANIFEST" "$BRANCH_LOG" \
  "$branch_rc" "$graph_rc" "$before_kb" "$after_kb" <<'PY'
from __future__ import annotations
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sha, report, manifest, branch_log, branch_rc, graph_rc, before_kb, after_kb = sys.argv[1:]
counts = {}
if Path(manifest).exists():
    with open(manifest, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            action = row.get("action", "unknown")
            counts[action] = counts.get(action, 0) + 1

payload = {
    "status": "success" if int(branch_rc) == 0 and int(graph_rc) == 0 else "warning",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "sha": sha,
    "branch_hygiene": {
        "exit_code": int(branch_rc),
        "manifest": manifest,
        "log": branch_log,
        "counts": counts,
    },
    "graphify_exit_code": int(graph_rc),
    "disk_used_kb_before": int(before_kb),
    "disk_used_kb_after": int(after_kb),
    "docker_volumes_pruned": False,
    "archive_old_unique": False,
}
Path(report).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
os.chmod(report, 0o600)
print(json.dumps({"status":payload["status"],"report":report,"counts":counts}, ensure_ascii=False))
PY

[ "$branch_rc" -eq 0 ] && [ "$graph_rc" -eq 0 ]
