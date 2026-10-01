#!/usr/bin/env bash
set -Eeuo pipefail

EXPECTED_SHA="${1:?uso: post_deploy_smoke.sh <sha>}"
APP_DIR="${APP_DIR:-/opt/ejc}"
DOMAIN="${EJC_DOMAIN:-ejc.depaulateixeira.adv.br}"
REPORT_DIR="${EJC_MAINT_REPORT_DIR:-/var/lib/ejc-maintenance}"
mkdir -p "$REPORT_DIR"
REPORT="$REPORT_DIR/post-deploy-smoke-${EXPECTED_SHA}.json"
EVIDENCE="$REPORT_DIR/release-evidence-${EXPECTED_SHA}.json"
TMP_LOG="$(mktemp /tmp/ejc-post-deploy-smoke.XXXXXX)"
cleanup(){ rm -f "$TMP_LOG"; }
trap cleanup EXIT

cd "$APP_DIR"

# 1) Identidade imutável da release.
IDENTITY_JSON="$(python3 scripts/check_release_identity.py \
  --expected "$EXPECTED_SHA" \
  --app-dir "$APP_DIR" \
  --public-url "https://${DOMAIN}/api/health")"

# 2) Smoke funcional seguro: containers, liveness/readiness, 11 entradas SPA,
# login inválido e compilação dos módulos críticos. Não cria/edita dados.
EJC_DOMAIN="$DOMAIN" bash scripts/post_deploy_check.sh >"$TMP_LOG" 2>&1

# 3) Evidência operacional ampliada. Falha aqui NÃO desfaz release saudável:
# backup/restore timers pertencem à continuidade e são reportados separadamente.
evidence_rc=0
python3 scripts/release_evidence.py --sha "$EXPECTED_SHA" --output "$EVIDENCE" \
  >/tmp/ejc-release-evidence.out 2>&1 || evidence_rc=$?

python3 - "$EXPECTED_SHA" "$REPORT" "$EVIDENCE" "$evidence_rc" "$TMP_LOG" "$IDENTITY_JSON" <<'PY'
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sha, report, evidence, evidence_rc, smoke_log, identity_raw = sys.argv[1:]
try:
    identity = json.loads(identity_raw)
except json.JSONDecodeError:
    identity = {"status": "error", "raw": identity_raw[:1000]}

payload = {
    "status": "success",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "sha": sha,
    "identity": identity,
    "http_smoke": {
        "status": "success",
        "log_tail": Path(smoke_log).read_text(encoding="utf-8", errors="replace")[-8000:],
    },
    "release_evidence": {
        "path": evidence,
        "exit_code": int(evidence_rc),
        "status": "success" if int(evidence_rc) == 0 else "warning",
    },
    "browser_contract": "frontend-e2e/full-CI; no production credentials or mutations",
}
Path(report).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
os.chmod(report, 0o600)
print(json.dumps({"status":"success","report":report,"evidence_rc":int(evidence_rc)}, ensure_ascii=False))
PY

echo "post-deploy smoke: OK — $REPORT"
