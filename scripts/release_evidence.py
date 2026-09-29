#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

APP_DIR = Path(os.getenv("EJC_APP_DIR", "/opt/ejc"))
REQUIRED_CONTAINERS = {
    "ejc_backend",
    "ejc_db",
    "ejc_frontend",
    "ejc_redis",
    "ejc_worker",
}
RESTORE_MAX_AGE = timedelta(days=9)


def run(args: list[str], timeout: int = 30) -> tuple[int, str]:
    try:
        p = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
        return p.returncode, (p.stdout or p.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except OSError as exc:
        return 127, type(exc).__name__


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


def parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sha", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    try:
        deployed = (APP_DIR / ".deployed_sha").read_text(encoding="utf-8").strip()
    except OSError:
        deployed = ""

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

    by_name = {str(c.get("Name") or ""): c for c in containers}
    essential_ok = True
    for name in REQUIRED_CONTAINERS:
        item = by_name.get(name)
        if not item:
            essential_ok = False
            break
        state = str(item.get("State") or "").lower()
        health_state = str(item.get("Health") or "").lower()
        if state != "running" or health_state == "unhealthy":
            essential_ok = False
            break

    rc_alembic, alembic = run(
        ["docker", "compose", "exec", "-T", "backend", "alembic", "current"],
        timeout=60,
    )
    rc_restore, restore_state = run([
        "systemctl",
        "show",
        "ejc-restore-drill-offsite.service",
        "-p",
        "Result",
        "-p",
        "ExecMainStatus",
        "--no-pager",
    ])
    restore_report = latest_json_from_journal("ejc-restore-drill-offsite.service")
    restore_at = parse_timestamp((restore_report or {}).get("executado_em"))
    restore_fresh = bool(
        restore_at
        and timedelta(0) <= (now - restore_at) <= RESTORE_MAX_AGE
    )

    ready_checks = ready.get("checks") if isinstance(ready, dict) else {}
    ready_blockers_ok = bool(
        isinstance(ready_checks, dict)
        and ready_checks.get("database") is True
        and ready_checks.get("migrations") is True
    )

    checks = {
        "sha_matches": deployed == args.sha == health.get("commit") == public.get("commit"),
        "health_local": health_ok and health.get("status") == "ok",
        "readiness": ready_ok and ready.get("status") == "ready" and ready_blockers_ok,
        "health_public": public_ok and public.get("status") == "ok",
        "containers": rc_ps == 0 and essential_ok,
        "alembic_head": rc_alembic == 0 and "(head)" in alembic,
        "restore_drill": (
            rc_restore == 0
            and "Result=success" in restore_state
            and bool(restore_report)
            and restore_report.get("status") == "sucesso"
            and restore_fresh
        ),
    }

    payload = {
        "status": "success" if all(checks.values()) else "failed",
        "generated_at": now.isoformat(),
        "sha": args.sha,
        "deployed_sha": deployed,
        "checks": checks,
        "health": health,
        "readiness": ready,
        "containers": [
            {
                "name": c.get("Name"),
                "state": c.get("State"),
                "health": c.get("Health"),
                "status": c.get("Status"),
            }
            for c in containers
        ],
        "alembic": alembic,
        "restore_drill": {
            **(restore_report or {}),
            "fresh": restore_fresh,
            "max_age_days": int(RESTORE_MAX_AGE.total_seconds() // 86400),
        },
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(output, 0o600)
    print(json.dumps(
        {"status": payload["status"], "output": str(output), "checks": checks},
        ensure_ascii=False,
    ))
    return 0 if payload["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
