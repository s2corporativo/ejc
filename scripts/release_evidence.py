#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, subprocess, urllib.request
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path(os.getenv("EJC_APP_DIR", "/opt/ejc"))

def run(args: list[str], timeout: int = 30) -> tuple[int, str]:
    p = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    return p.returncode, (p.stdout or p.stderr or "").strip()

def get_json(url: str) -> tuple[bool, dict]:
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
            return response.status == 200, data
    except Exception as exc:
        return False, {"error_type": type(exc).__name__}

def latest_json_from_journal(unit: str) -> dict | None:
    rc, out = run(["journalctl", "-u", unit, "-n", "80", "--no-pager", "-o", "cat"])
    if rc != 0:
        return None
    for line in reversed(out.splitlines()):
        start = line.find("{")
        if start < 0:
            continue
        try:
            value = json.loads(line[start:])
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            continue
    return None

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sha", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    deployed = (APP_DIR / ".deployed_sha").read_text(encoding="utf-8").strip()
    health_ok, health = get_json("http://127.0.0.1:8000/api/health")
    ready_ok, ready = get_json("http://127.0.0.1:8000/api/health/ready")
    public_ok, public = get_json("https://ejc.depaulateixeira.adv.br/api/health")

    rc_ps, ps_raw = run(["docker", "compose", "ps", "--format", "json"])
    containers = []
    if rc_ps == 0:
        for line in ps_raw.splitlines():
            try:
                containers.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    rc_alembic, alembic = run(["docker", "compose", "exec", "-T", "backend", "alembic", "current"], timeout=60)
    rc_restore, restore_state = run(["systemctl", "show", "ejc-restore-drill-offsite.service", "-p", "Result", "-p", "ExecMainStatus", "--no-pager"])
    restore_report = latest_json_from_journal("ejc-restore-drill-offsite.service")

    container_bad = [
        c.get("Name") for c in containers
        if "unhealthy" in str(c.get("Health", c.get("Status", ""))).lower()
        or "exited" in str(c.get("State", c.get("Status", ""))).lower()
    ]
    checks = {
        "sha_matches": deployed == args.sha == health.get("commit") == public.get("commit"),
        "health_local": health_ok and health.get("status") == "ok",
        "readiness": ready_ok and ready.get("status") == "ready" and all(ready.get("checks", {}).values()),
        "health_public": public_ok and public.get("status") == "ok",
        "containers": rc_ps == 0 and len(containers) >= 5 and not container_bad,
        "alembic_head": rc_alembic == 0 and "(head)" in alembic,
        "restore_drill": rc_restore == 0 and "Result=success" in restore_state and bool(restore_report) and restore_report.get("status") == "sucesso",
    }
    payload = {
        "status": "success" if all(checks.values()) else "failed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sha": args.sha,
        "deployed_sha": deployed,
        "checks": checks,
        "health": health,
        "readiness": ready,
        "containers": [{"name": c.get("Name"), "state": c.get("State"), "health": c.get("Health"), "status": c.get("Status")} for c in containers],
        "alembic": alembic,
        "restore_drill": restore_report,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(output, 0o600)
    print(json.dumps({"status": payload["status"], "output": str(output), "checks": checks}, ensure_ascii=False))
    return 0 if payload["status"] == "success" else 1

if __name__ == "__main__":
    raise SystemExit(main())
