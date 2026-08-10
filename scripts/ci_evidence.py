#!/usr/bin/env python3
"""Evidência local imutável do fallback de CI do EJC.

Responsabilidades:
- criar tentativas isoladas por SHA;
- tornar a tentativa recém-criada a única tentativa promovível;
- escrever ponteiros/summary atomicamente com fsync;
- exigir os oito logs do full gate para sucesso;
- calcular/verificar hashes em streaming;
- localizar o log relevante da tentativa atual;
- podar evidências antigas sem seguir symlinks nem remover SHA em execução.

Invariante central: ``sucesso A -> tentativa B`` invalida A imediatamente, mesmo
antes de B produzir logs. Assim uma falha posterior nunca reutiliza verde antigo.

Complexidade:
- start/pointer: O(1);
- finish/verify: O(B) em tempo, B = bytes dos logs, O(1 MiB) memória adicional;
- prune: O(S + F_removidos), S = SHAs armazenados.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import pathlib
import secrets
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Final

_CHUNK: Final[int] = 1024 * 1024
_REQUIRED_SUCCESS_LOGS: Final[frozenset[str]] = frozenset(
    {
        "backend.log",
        "eval.log",
        "frontend.log",
        "p0.log",
        "governanca.log",
        "architecture.log",
        "continuity.log",
        "ui-extra.log",
    }
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_sha(value: str) -> str:
    if len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError("SHA deve conter exatamente 40 caracteres hexadecimais minúsculos")
    return value


def _is_sha_dir(path: pathlib.Path) -> bool:
    try:
        _validate_sha(path.name)
    except ValueError:
        return False
    return path.is_dir() and not path.is_symlink()


def _hash_file(path: pathlib.Path) -> tuple[str, int]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"arquivo de evidência inválido: {path}")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _fsync_directory(directory: pathlib.Path) -> None:
    try:
        fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    tmp = pathlib.Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        _fsync_directory(path.parent)
    finally:
        if tmp.exists():
            tmp.unlink()


def _read_json_file(path: pathlib.Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"arquivo JSON inválido: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON precisa ser objeto: {path}")
    return value


def _resolve_child(base: pathlib.Path, relative: str) -> pathlib.Path:
    rel = pathlib.PurePosixPath(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("caminho relativo inseguro")
    resolved_base = base.resolve()
    resolved = (resolved_base / pathlib.Path(*rel.parts)).resolve()
    if resolved != resolved_base and resolved_base not in resolved.parents:
        raise ValueError("caminho escapou da raiz de evidência")
    return resolved


def _remove_tree_no_follow(path: pathlib.Path) -> None:
    if path.is_symlink():
        path.unlink()
        return
    with os.scandir(path) as entries:
        for entry in entries:
            child = pathlib.Path(entry.path)
            if entry.is_symlink():
                child.unlink()
            elif entry.is_dir(follow_symlinks=False):
                _remove_tree_no_follow(child)
            else:
                child.unlink()
    path.rmdir()


def _attempts_root(sha_root: pathlib.Path) -> pathlib.Path:
    return (sha_root.resolve() / "attempts").resolve()


def _resolve_current_attempt(sha_root: pathlib.Path, sha: str) -> pathlib.Path:
    sha = _validate_sha(sha)
    sha_root = sha_root.resolve()
    pointer = _read_json_file(sha_root / "latest-attempt.json")
    if pointer.get("schema") != 1 or pointer.get("target_sha") != sha:
        raise ValueError("latest-attempt não corresponde ao SHA")
    attempt = _resolve_child(sha_root, str(pointer["attempt"]))
    attempts_root = _attempts_root(sha_root)
    if attempts_root not in attempt.parents or attempt.is_symlink() or not attempt.is_dir():
        raise ValueError("tentativa atual fora da raiz ou inválida")
    return attempt


def start_attempt(root: pathlib.Path, sha: str, ref: str, pr: int | None) -> pathlib.Path:
    sha = _validate_sha(sha)
    raw_root = root.expanduser()
    if raw_root.is_symlink():
        raise ValueError("raiz de evidência não pode ser symlink")
    root = raw_root.resolve()
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
    attempts_root = _attempts_root(sha_root)
    if attempts_root not in attempt.parents or attempt.is_symlink() or not attempt.is_dir():
        raise ValueError("tentativa fora da raiz de evidência")
    if attempt != _resolve_current_attempt(sha_root, sha):
        raise ValueError("tentativa stale: outra tentativa já é a atual")
    if result not in {"success", "failure"}:
        raise ValueError("result inválido")
    if result == "success" and exit_code != 0:
        raise ValueError("sucesso exige exit_code=0")
    if promote and result != "success":
        raise ValueError("somente sucesso pode atualizar latest-success")

    log_paths = sorted(attempt.glob("*.log"))
    log_names = {path.name for path in log_paths}
    if result == "success" and log_names != _REQUIRED_SUCCESS_LOGS:
        missing = sorted(_REQUIRED_SUCCESS_LOGS - log_names)
        extra = sorted(log_names - _REQUIRED_SUCCESS_LOGS)
        raise ValueError(
            "sucesso exige exatamente os oito logs do full gate; "
            f"missing={missing}, extra={extra}"
        )

    logs: dict[str, dict[str, int | str]] = {}
    for path in log_paths:
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
                "schema": 2,
                "target_sha": sha,
                "attempt": attempt.relative_to(sha_root).as_posix(),
                "summary": summary.relative_to(sha_root).as_posix(),
                "summary_sha256": summary_hash,
                "promoted_at": _utc_now(),
            },
        )
    return summary


def verify_success(sha_root: pathlib.Path, sha: str) -> bool:
    sha = _validate_sha(sha)
    sha_root = sha_root.resolve()
    try:
        current_attempt = _resolve_current_attempt(sha_root, sha)
        latest = _read_json_file(sha_root / "latest-success.json")
        if latest.get("schema") != 2 or latest.get("target_sha") != sha:
            return False

        success_attempt = _resolve_child(sha_root, str(latest["attempt"]))
        if success_attempt != current_attempt:
            return False

        summary = _resolve_child(sha_root, str(latest["summary"]))
        attempts_root = _attempts_root(sha_root)
        if attempts_root not in summary.parents:
            return False
        if summary.parent != current_attempt or summary.is_symlink() or not summary.is_file():
            return False

        summary_hash, _ = _hash_file(summary)
        if summary_hash != latest.get("summary_sha256"):
            return False

        obj = _read_json_file(summary)
        if (
            obj.get("schema") != 2
            or obj.get("target_sha") != sha
            or obj.get("result") != "success"
            or obj.get("exit_code") != 0
        ):
            return False

        logs = obj.get("logs")
        if not isinstance(logs, dict) or set(logs) != _REQUIRED_SUCCESS_LOGS:
            return False
        for name in _REQUIRED_SUCCESS_LOGS:
            meta = logs.get(name)
            if not isinstance(meta, dict):
                return False
            path = _resolve_child(summary.parent, name)
            if path.parent != summary.parent or path.is_symlink() or not path.is_file():
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
    try:
        attempt = _resolve_current_attempt(sha_root, sha)
        summary_path = attempt / "summary.json"
        if summary_path.is_file() and not summary_path.is_symlink():
            summary = _read_json_file(summary_path)
            if summary.get("target_sha") == sha and summary.get("result") == "failure":
                stage = summary.get("failed_stage")
                if isinstance(stage, str) and stage:
                    candidate = _resolve_child(attempt, f"{stage}.log")
                    if candidate.parent == attempt and candidate.is_file() and not candidate.is_symlink():
                        return candidate
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


def _protected_attempt_names(sha_root: pathlib.Path) -> set[str]:
    protected: set[str] = set()
    pointer_specs = (
        ("latest-attempt.json", ("attempt",)),
        ("latest-success.json", ("attempt", "summary")),
    )
    for pointer_name, keys in pointer_specs:
        pointer = sha_root / pointer_name
        if not pointer.is_file() or pointer.is_symlink():
            continue
        try:
            obj = _read_json_file(pointer)
            for key in keys:
                if key not in obj:
                    continue
                rel = pathlib.PurePosixPath(str(obj[key]))
                if rel.is_absolute() or ".." in rel.parts:
                    continue
                if len(rel.parts) >= 2 and rel.parts[0] == "attempts":
                    protected.add(rel.parts[1])
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue
    return protected


def _quarantine_sha_root(root: pathlib.Path, sha_root: pathlib.Path) -> pathlib.Path:
    quarantine = root / f".prune-{sha_root.name}-{os.getpid()}-{secrets.token_hex(4)}"
    os.replace(sha_root, quarantine)
    _fsync_directory(root)
    return quarantine


def prune_evidence(
    root: pathlib.Path,
    max_shas: int,
    max_age_days: int,
    attempts_per_sha: int,
) -> dict[str, int]:
    if max_shas < 1 or max_age_days < 1 or attempts_per_sha < 1:
        raise ValueError("limites de retenção devem ser >= 1")
    raw_root = root.expanduser()
    if raw_root.is_symlink():
        raise ValueError("raiz de evidência não pode ser symlink")
    root = raw_root.resolve()
    if not root.is_dir():
        return {"removed_shas": 0, "removed_attempts": 0, "skipped_locked": 0}

    cutoff = time.time() - max_age_days * 86400
    sha_dirs = [path for path in root.iterdir() if _is_sha_dir(path)]
    sha_dirs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    keep_by_count = {path.name for path in sha_dirs[:max_shas]}
    stats = {"removed_shas": 0, "removed_attempts": 0, "skipped_locked": 0}

    for sha_root in sha_dirs:
        if not sha_root.exists():
            continue
        lock_path = sha_root / ".lock"
        lock_path.touch(mode=0o600, exist_ok=True)
        quarantine: pathlib.Path | None = None
        with lock_path.open("a+") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                stats["skipped_locked"] += 1
                continue

            if not sha_root.exists():
                continue
            if sha_root.name not in keep_by_count and sha_root.stat().st_mtime < cutoff:
                quarantine = _quarantine_sha_root(root, sha_root)
            else:
                attempts = sha_root / "attempts"
                if not attempts.is_dir() or attempts.is_symlink():
                    continue
                protected = _protected_attempt_names(sha_root)
                attempt_dirs = [
                    path
                    for path in attempts.iterdir()
                    if path.is_dir() and not path.is_symlink()
                ]
                attempt_dirs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
                kept_non_protected = 0
                for attempt in attempt_dirs:
                    if attempt.name in protected:
                        continue
                    if kept_non_protected < attempts_per_sha:
                        kept_non_protected += 1
                        continue
                    if attempt.stat().st_mtime >= cutoff:
                        continue
                    _remove_tree_no_follow(attempt)
                    stats["removed_attempts"] += 1

        if quarantine is not None:
            _remove_tree_no_follow(quarantine)
            _fsync_directory(root)
            stats["removed_shas"] += 1
    return stats


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

    prune = sub.add_parser("prune")
    prune.add_argument("--root", required=True, type=pathlib.Path)
    prune.add_argument("--max-shas", type=int, default=200)
    prune.add_argument("--max-age-days", type=int, default=30)
    prune.add_argument("--attempts-per-sha", type=int, default=5)
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
        if args.command == "prune":
            print(
                json.dumps(
                    prune_evidence(
                        args.root,
                        args.max_shas,
                        args.max_age_days,
                        args.attempts_per_sha,
                    ),
                    sort_keys=True,
                )
            )
            return 0
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"[ci-evidence] ERRO: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
