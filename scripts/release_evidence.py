#!/usr/bin/env python3
"""Coleta evidência sanitizada de release/observabilidade do EJC.

Somente leitura. Não imprime nem persiste segredos. Em modo release, falha
fechado se SHA/health/readiness/containers/nginx/backup/restore drill não
estiverem íntegros. Em modo monitor, usa os mesmos gates sem exigir SHA alvo.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

APP_DIR = Path(os.getenv("EJC_APP_DIR", "/opt/ejc"))
DEFAULT_OUTPUT_DIR = Path(
    os.getenv("EJC_EVIDENCE_DIR", "/var/lib/ejc-release-evidence")
)
REQUIRED_CONTAINERS = {
    "ejc_backend",
    "ejc_db",
    "ejc_frontend",
    "ejc_redis",
    "ejc_worker",
}


def _run(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 60,
    input_text: str | None = None,
) -> tuple[int, str, str]:
    proc = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _fetch_json(url: str, timeout: int = 10) -> dict[str, Any]:
    req = Request(url, headers={"User-Agent": "ejc-release-evidence/1"})
    with urlopen(req, timeout=timeout) as response:
        body = response.read(256 * 1024)
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise RuntimeError("JSON não é objeto")
    return parsed


def _parse_kv(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip()
    return result


def _last_restore_report() -> dict[str, Any] | None:
    rc, out, _ = _run(
        [
            "journalctl",
            "-u",
            "ejc-restore-drill-offsite.service",
            "-n",
            "120",
            "--no-pager",
            "-o",
            "cat",
        ],
        timeout=20,
    )
    if rc != 0:
        return None
    for line in reversed(out.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and value.get("status") in {"sucesso", "erro"}:
            return {
                key: value.get(key)
                for key in (
                    "status",
                    "arquivo",
                    "alembic_version",
                    "tabelas_publicas",
                    "executado_em",
                    "duracao_segundos",
                    "remote_bytes",
                    "dump_bytes",
                )
                if key in value
            }
    return None


def _restore_age_hours(report: dict[str, Any] | None) -> float | None:
    if not report or not report.get("executado_em"):
        return None
    try:
        dt = datetime.fromisoformat(
            str(report["executado_em"]).replace("Z", "+00:00")
        )
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return round(
            (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()
            / 3600,
            2,
        )
    except (TypeError, ValueError):
        return None


def _compose_ps() -> list[dict[str, Any]]:
    rc, out, err = _run(
        ["docker", "compose", "ps", "--format", "json"],
        cwd=APP_DIR,
        timeout=30,
    )
    if rc != 0:
        raise RuntimeError(f"docker compose ps falhou: {err[:200]}")
    rows: list[dict[str, Any]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _backup_probe() -> dict[str, Any]:
    probe = APP_DIR / "scripts/backup/check_backup_health.py"
    if not probe.is_file():
        return {"ok": False, "problemas": ["probe de backup ausente"]}
    rc, out, _ = _run(
        ["docker", "exec", "-i", "ejc_backend", "python", "-"],
        timeout=90,
        input_text=probe.read_text(encoding="utf-8"),
    )
    try:
        value = json.loads(out.splitlines()[-1]) if out else {}
    except (json.JSONDecodeError, IndexError):
        value = {}
    if not isinstance(value, dict):
        value = {}
    value["exit_code"] = rc
    return value


def _self_test() -> int:
    sample = (
        "Result=success\nExecMainStatus=0\n"
        "SubState=dead\nActiveState=inactive\n"
    )
    assert _parse_kv(sample)["Result"] == "success"
    assert _parse_kv(sample)["ExecMainStatus"] == "0"
    assert _restore_age_hours(
        {"executado_em": datetime.now(timezone.utc).isoformat()}
    ) is not None
    print('{"status":"sucesso","self_test":true}')
    return 0


def collect(expected_sha: str | None) -> tuple[dict[str, Any], list[str]]:
    problems: list[str] = []
    now = datetime.now(timezone.utc)

    deployed_sha = ""
    marker = APP_DIR / ".deployed_sha"
    if marker.is_file():
        deployed_sha = marker.read_text(encoding="utf-8").strip()

    if expected_sha and deployed_sha != expected_sha:
        problems.append(
            f"SHA publicado diverge do esperado: {deployed_sha or 'ausente'}"
        )

    try:
        health = _fetch_json("http://127.0.0.1:8000/api/health")
    except Exception as exc:  # noqa: BLE001
        health = {"status": "erro", "erro": type(exc).__name__}
        problems.append("health local indisponível")

    try:
        ready = _fetch_json("http://127.0.0.1:8000/api/health/ready")
    except Exception as exc:  # noqa: BLE001
        ready = {"status": "erro", "erro": type(exc).__name__}
        problems.append("readiness local indisponível")

    if health.get("status") != "ok":
        problems.append("liveness não está ok")
    if deployed_sha and health.get("commit") not in {deployed_sha, None, ""}:
        problems.append("commit do /api/health diverge de .deployed_sha")
    if ready.get("status") != "ready":
        problems.append("readiness não está ready")
    checks = ready.get("checks")
    if isinstance(checks, dict):
        for name, ok in checks.items():
            if ok is not True:
                problems.append(f"readiness falhou: {name}")

    try:
        containers = _compose_ps()
    except Exception as exc:  # noqa: BLE001
        containers = []
        problems.append(f"docker compose ps indisponível: {type(exc).__name__}")

    by_name = {
        str(item.get("Name") or item.get("Names") or ""): item for item in containers
    }
    for name in sorted(REQUIRED_CONTAINERS):
        item = by_name.get(name)
        if not item:
            problems.append(f"container obrigatório ausente: {name}")
            continue
        state = str(item.get("State") or item.get("Status") or "").lower()
        if "running" not in state and not state.startswith("up"):
            problems.append(f"container não está running: {name}")

    rc_nginx, _, nginx_err = _run(["nginx", "-t"], timeout=20)
    nginx = {"ok": rc_nginx == 0}
    if rc_nginx != 0:
        nginx["erro"] = nginx_err[:300]
        problems.append("nginx -t falhou")

    rc_alembic, alembic_out, alembic_err = _run(
        ["docker", "compose", "exec", "-T", "backend", "alembic", "current"],
        cwd=APP_DIR,
        timeout=60,
    )
    alembic = {
        "ok": rc_alembic == 0,
        "current": alembic_out.splitlines()[-1] if alembic_out else "",
    }
    if rc_alembic != 0:
        alembic["erro"] = alembic_err[:300]
        problems.append("alembic current falhou")

    rc_deploy, deploy_out, _ = _run(
        [
            "systemctl",
            "show",
            "ejc-deploy-approved.service",
            "-p",
            "Result",
            "-p",
            "ExecMainStatus",
        ],
        timeout=20,
    )
    deploy_service = _parse_kv(deploy_out) if rc_deploy == 0 else {}
    if deploy_service.get("Result") not in {"success", ""}:
        problems.append("último serviço de deploy não terminou em success")

    rc_restore, restore_out, _ = _run(
        [
            "systemctl",
            "show",
            "ejc-restore-drill-offsite.service",
            "-p",
            "Result",
            "-p",
            "ExecMainStatus",
        ],
        timeout=20,
    )
    restore_service = _parse_kv(restore_out) if rc_restore == 0 else {}
    restore_report = _last_restore_report()
    restore_age = _restore_age_hours(restore_report)
    if restore_service.get("Result") != "success":
        problems.append("restore drill off-site não possui último resultado success")
    if not restore_report or restore_report.get("status") != "sucesso":
        problems.append("relatório do restore drill off-site ausente/sem sucesso")
    elif restore_age is None or restore_age > 8 * 24:
        problems.append("restore drill off-site está vencido (>8 dias)")

    backup = _backup_probe()
    if not backup.get("ok") or int(backup.get("exit_code", 1)) != 0:
        problems.append("sonda de backup não está íntegra")

    disk = shutil.disk_usage("/")
    disk_free_pct = round((disk.free / disk.total) * 100, 2) if disk.total else 0.0
    if disk_free_pct < 10:
        problems.append("disco raiz com menos de 10% livre")

    report = {
        "schema": "ejc.release-evidence.v1",
        "mode": "release" if expected_sha else "monitor",
        "generated_at": now.isoformat(),
        "ok": not problems,
        "expected_sha": expected_sha,
        "deployed_sha": deployed_sha or None,
        "health": health,
        "ready": ready,
        "containers": [
            {
                "name": item.get("Name") or item.get("Names"),
                "service": item.get("Service"),
                "state": item.get("State"),
                "status": item.get("Status"),
                "health": item.get("Health"),
            }
            for item in containers
        ],
        "nginx": nginx,
        "alembic": alembic,
        "deploy_service": deploy_service,
        "backup": backup,
        "restore_drill": {
            "service": restore_service,
            "last_report": restore_report,
            "age_hours": restore_age,
        },
        "disk": {"root_free_percent": disk_free_pct},
        "problems": problems,
    }
    return report, problems


def _write_report(
    report: dict[str, Any], output_dir: Path, *, mode: str
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(output_dir, 0o700)
    latest = output_dir / "latest.json"
    latest.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(latest, 0o600)

    if mode == "release":
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        sha = str(report.get("deployed_sha") or "unknown")[:12]
        target = output_dir / f"release-{stamp}-{sha}.json"
        target.write_text(latest.read_text(encoding="utf-8"), encoding="utf-8")
        os.chmod(target, 0o600)
        releases = sorted(output_dir.glob("release-*.json"), reverse=True)
        for old in releases[50:]:
            old.unlink(missing_ok=True)
        return target
    return latest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("release", "monitor"), default="monitor")
    parser.add_argument("--expected-sha")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return _self_test()
    if args.mode == "release" and not args.expected_sha:
        parser.error("--mode release exige --expected-sha")

    report, problems = collect(
        args.expected_sha.strip() if args.expected_sha else None
    )
    path = _write_report(report, args.output_dir, mode=args.mode)
    print(
        json.dumps(
            {
                "status": "sucesso" if not problems else "erro",
                "evidence": str(path),
                "deployed_sha": report.get("deployed_sha"),
                "problems": problems,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
