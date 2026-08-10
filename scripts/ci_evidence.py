#!/usr/bin/env python3
"""Evidência local imutável do fallback de CI do EJC.

Este módulo não conhece GitHub nem executa testes. Ele é responsável somente por:
- criar tentativas isoladas por SHA;
- escrever ponteiros/summary de forma atômica;
- calcular hashes de logs em streaming;
- verificar integridade de uma evidência de sucesso;
- localizar o log mais recente da tentativa atual.

Complexidade: O(total de bytes dos logs) em tempo e O(1 MiB) de memória adicional
por hashing, independentemente do tamanho da suíte.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import secrets
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any

_CHUNK = 1024 * 1024


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_sha(value: str) -> str:
    if len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError("SHA deve conter exatamente 40 caracteres hexadecimais minúsculos")
    return value


def _hash_file(path: pathlib.Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = pathlib.Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _resolve_child(base: pathlib.Path, relative: str) -> pathlib.Path:
    rel = pathlib.PurePosixPath(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("caminho relativo inseguro")
    resolved = (base / pathlib.Path(*rel.parts)).resolve()
    if resolved != base and base not in resolved.parents:
        raise ValueError("caminho escapou da raiz de evidência")
    return resolved


def start_attempt(root: pathlib.Path, sha: str, ref: str, pr: int | None) -> pathlib.Path:
    sha = _validate_sha(sha)
    root = root.resolve()
    sha_root = root / sha
    attempts = sha_root / "attempts"
    attempts.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(sha_root, 0o700)
    os.chmod(attempts, 0o700)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    attempt_id = f"{stamp}-{os.getpid()}-{secrets.token_hex(4)}"
    attempt = attempts / attempt_id
    attempt.mkdir(mode=0o700)

    _atomic_json(
        sha_root / "latest-attempt.json",
        {
            "schema": 1,
            "target_sha": sha,
            "attempt": attempt.relative_to(sha_root).as_posix(),
            "ref": ref,
            "pr": pr,
            "started_at": _utc_now(),
        },
    )
    return attempt


def finish_attempt(
    attempt: pathlib.Path,
    sha_root: pathlib.Path,
    sha: str,
    ref: str,
    pr: int | None,
    result: str,
    failed_stage: str | None,
    exit_code: int,
    promote: bool,
) -> pathlib.Path:
    sha = _validate_sha(sha)
    attempt = attempt.resolve()
    sha_root = sha_root.resolve()
    attempts_root = (sha_root / "attempts").resolve()
    if attempts_root not in attempt.parents:
        raise ValueError("tentativa fora da raiz de evidência")
    if result not in {"success", "failure"}:
        raise ValueError("result inválido")
    if promote and result != "success":
        raise ValueError("somente sucesso pode atualizar latest-success")

    logs: dict[str, dict[str, int | str]] = {}
    for path in sorted(attempt.glob("*.log")):
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"log inválido: {path.name}")
        digest, size = _hash_file(path)
        logs[path.name] = {"sha256": digest, "bytes": size}

    summary_obj: dict[str, Any] = {
        "schema": 2,
        "target_sha": sha,
        "ref": ref,
        "pr": pr,
        "completed_at": _utc_now(),
        "result": result,
        "failed_stage": failed_stage,
        "exit_code": exit_code,
        "logs": logs,
    }
    summary = attempt / "summary.json"
    _atomic_json(summary, summary_obj)

    if promote:
        summary_hash, _ = _hash_file(summary)
        _atomic_json(
            sha_root / "latest-success.json",
            {
                "schema": 1,
                "target_sha": sha,
                "summary": summary.relative_to(sha_root).as_posix(),
                "summary_sha256": summary_hash,
                "promoted_at": _utc_now(),
            },
        )
    return summary


def verify_success(sha_root: pathlib.Path, sha: str) -> bool:
    sha = _validate_sha(sha)
    sha_root = sha_root.resolve()
    pointer = sha_root / "latest-success.json"
    if not pointer.is_file() or pointer.is_symlink():
        return False
    try:
        latest = json.loads(pointer.read_text(encoding="utf-8"))
        if latest.get("target_sha") != sha:
            return False
        summary = _resolve_child(sha_root, str(latest["summary"]))
        attempts_root = (sha_root / "attempts").resolve()
        if attempts_root not in summary.parents or not summary.is_file() or summary.is_symlink():
            return False
        summary_hash, _ = _hash_file(summary)
        if summary_hash != latest.get("summary_sha256"):
            return False
        obj = json.loads(summary.read_text(encoding="utf-8"))
        if obj.get("target_sha") != sha or obj.get("result") != "success" or obj.get("exit_code") != 0:
            return False
        for name, meta in (obj.get("logs") or {}).items():
            path = _resolve_child(summary.parent, name)
            if path.parent != summary.parent or not path.is_file() or path.is_symlink():
                return False
            digest, size = _hash_file(path)
            if digest != meta.get("sha256") or size != int(meta.get("bytes", -1)):
                return False
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return False
    return True


def latest_log(sha_root: pathlib.Path, sha: str, started_epoch: int) -> pathlib.Path | None:
    sha = _validate_sha(sha)
    sha_root = sha_root.resolve()
    pointer = sha_root / "latest-attempt.json"
    if not pointer.is_file() or pointer.is_symlink():
        return None
    try:
        obj = json.loads(pointer.read_text(encoding="utf-8"))
        if obj.get("target_sha") != sha:
            return None
        attempt = _resolve_child(sha_root, str(obj["attempt"]))
        attempts_root = (sha_root / "attempts").resolve()
        if attempts_root not in attempt.parents or not attempt.is_dir() or attempt.is_symlink():
            return None
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None

    best: pathlib.Path | None = None
    best_mtime = float(started_epoch - 1)
    for path in attempt.glob("*.log"):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime >= started_epoch and mtime >= best_mtime:
            best = path
            best_mtime = mtime
    return best


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start")
    start.add_argument("--root", required=True, type=pathlib.Path)
    start.add_argument("--sha", required=True)
    start.add_argument("--ref", default="")
    start.add_argument("--pr", type=int)

    finish = sub.add_parser("finish")
    finish.add_argument("--attempt", required=True, type=pathlib.Path)
    finish.add_argument("--sha-root", required=True, type=pathlib.Path)
    finish.add_argument("--sha", required=True)
    finish.add_argument("--ref", default="")
    finish.add_argument("--pr", type=int)
    finish.add_argument("--result", required=True, choices=("success", "failure"))
    finish.add_argument("--failed-stage")
    finish.add_argument("--exit-code", type=int, default=0)
    finish.add_argument("--promote", action="store_true")

    verify = sub.add_parser("verify")
    verify.add_argument("--sha-root", required=True, type=pathlib.Path)
    verify.add_argument("--sha", required=True)

    log = sub.add_parser("latest-log")
    log.add_argument("--sha-root", required=True, type=pathlib.Path)
    log.add_argument("--sha", required=True)
    log.add_argument("--started-epoch", required=True, type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "start":
            print(start_attempt(args.root, args.sha, args.ref, args.pr))
            return 0
        if args.command == "finish":
            print(
                finish_attempt(
                    args.attempt,
                    args.sha_root,
                    args.sha,
                    args.ref,
                    args.pr,
                    args.result,
                    args.failed_stage,
                    args.exit_code,
                    args.promote,
                )
            )
            return 0
        if args.command == "verify":
            return 0 if verify_success(args.sha_root, args.sha) else 1
        if args.command == "latest-log":
            path = latest_log(args.sha_root, args.sha, args.started_epoch)
            if path is None:
                return 1
            print(path)
            return 0
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"[ci-evidence] ERRO: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
