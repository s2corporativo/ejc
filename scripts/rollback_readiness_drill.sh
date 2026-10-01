#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="${APP_DIR:-/opt/ejc}"
REPORT_DIR="${EJC_MAINT_REPORT_DIR:-/var/lib/ejc-maintenance}"
MARKER="$APP_DIR/.rollback_last_sha"
mkdir -p "$REPORT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT="$REPORT_DIR/rollback-readiness-$STAMP.json"
name="ejc_rollback_probe_frontend_$$"
cleanup(){ docker rm -f "$name" >/dev/null 2>&1 || true; }
trap cleanup EXIT

sha="$(tr -d '\r\n' < "$MARKER" 2>/dev/null || true)"
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || { echo "rollback marker ausente/inválido" >&2; exit 2; }

for image in ejc-backend:rollback-last ejc-worker:rollback-last ejc-frontend:rollback-last; do
  docker image inspect "$image" >/dev/null
done

# Backend anterior responde ao health em processo isolado, SEM rede/DB.
docker run --rm --network none --entrypoint python   -e APP_ENV=development   -e GIT_SHA="$sha"   -e ENABLE_SCHEDULER=false   -e STARTUP_STEP_TIMEOUT_SECONDS=0.25   ejc-backend:rollback-last - <<'PY'
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    r=c.get("/api/health")
    assert r.status_code == 200, r.text
    assert r.json().get("commit")
PY

# Worker anterior precisa ao menos carregar o app/task registry.
docker run --rm --network none --entrypoint python   ejc-worker:rollback-last -c 'from app.core.celery_app import celery_app; assert celery_app.main'

# Frontend anterior sobe de verdade e serve o shell.
docker run --rm -d --name "$name" -p 127.0.0.1:18081:80 ejc-frontend:rollback-last >/dev/null
ok=0
for _ in $(seq 1 20); do
  if curl -fsS --max-time 3 http://127.0.0.1:18081/ >/dev/null; then ok=1; break; fi
  sleep 1
done
[ "$ok" = 1 ] || { echo "frontend rollback-last não respondeu" >&2; exit 3; }

python3 - "$REPORT" "$sha" <<'PY'
import json,os,sys
from datetime import datetime,timezone
from pathlib import Path
report,sha=sys.argv[1:]
payload={
  "status":"success",
  "generated_at":datetime.now(timezone.utc).isoformat(),
  "rollback_sha":sha,
  "backend_health_isolated":True,
  "worker_import":True,
  "frontend_http":True,
  "production_cutover_performed":False,
  "database_mutated":False,
}
Path(report).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
os.chmod(report,0o600)
print(json.dumps(payload))
PY
