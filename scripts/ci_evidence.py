#!/usr/bin/env python3
"""Evidência local imutável do fallback de CI do EJC.

Responsabilidades:
- criar tentativas isoladas por SHA;
- escrever ponteiros/summary atomicamente;
- calcular hashes em streaming;
- verificar integridade da prova de sucesso;
- localizar o log da tentativa atual;
- podar evidências antigas sem seguir symlinks nem remover SHA em execução.

Hashing: O(total de bytes) em tempo e O(1 MiB) de memória adicional.
Prune: O(S + F_removidos), onde S é o número de SHAs armazenados.
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
from typing import Any

_CHUNK = 1024 * 1024


def _utc_now() -> str:
    """Retorna timestamp UTC ISO-8601 com timezone explícito."""
    return datetime.now(timezone.utc).isoformat()


def _validate_sha(value: str) -> str:
    """Valida o identificador Git SHA-1 usado como namespace da evidência."""
    if len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError("SHA deve conter exatamente 40 caracteres hexadecimais minúsculos")
    return value


def _is_sha_dir(path: pathlib.Path) -> bool:
    """Retorna True apenas para diretório real cujo nome seja um SHA válido."""
    try:
        _validate_sha(path.name)
    except ValueError:
        return False
    return path.is_dir() and not path.is_symlink()


def _hash_file(path: pathlib.Path) -> tuple[str, int]:
    """Calcula SHA-256 e tamanho em streaming com memória adicional limitada."""
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    """Persiste JSON com fsync e rename atômico no mesmo filesystem."""
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
    """Resolve filho relativo sem permitir path traversal para fora de ``base``."""
    rel = pathlib.PurePosixPath(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("caminho relativo inseguro")
    resolved = (base / pathlib.Path(*rel.parts)).resolve()
    if resolved != base and base not in resolved.parents:
        raise ValueError("caminho escapou da raiz de evidência")
    return resolved


def _remove_tree_no_follow(path: pathlib.Path) -> None:
    """Remove árvore previamente validada sem atravessar symlinks."""
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


def start_attempt(root: pathlib.Path, sha: str, ref: str, pr: int | None) -> pathlib.Path:
    """Cria tentativa única e atualiza atomicamente o ponteiro ``latest-attempt``."""
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
    """Finaliza tentativa, hasheia logs e opcionalmente promove sucesso íntegro."""
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
    """Valida ponteiro, summary e todos os logs da última prova de sucesso."""
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
    """Localiza o log mais recente da tentativa atual iniciado após ``started_epoch``."""
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


def _protected_attempt_names(sha_root: pathlib.Path) -> set[str]:
    """Retorna IDs de tentativas referenciadas pelos ponteiros autoritativos."""
    protected: set[str] = set()
    for pointer_name, key in (("latest-success.json", "summary"), ("latest-attempt.json", "attempt")):
        pointer = sha_root / pointer_name
        if not pointer.is_file() or pointer.is_symlink():
            continue
        try:
            obj = json.loads(pointer.read_text(encoding="utf-8"))
            rel = pathlib.PurePosixPath(str(obj[key]))
            if rel.is_absolute() or ".." in rel.parts:
                continue
            if len(rel.parts) >= 2 and rel.parts[0] == "attempts":
                protected.add(rel.parts[1])
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue
    return protected


def _quarantine_sha_root(root: pathlib.Path, sha_root: pathlib.Path) -> pathlib.Path:
    """Retira atomicamente um SHA do namespace ativo antes da remoção física."""
    quarantine = root / f".prune-{sha_root.name}-{os.getpid()}-{secrets.token_hex(4)}"
    os.replace(sha_root, quarantine)
    return quarantine


def prune_evidence(
    root: pathlib.Path,
    max_shas: int,
    max_age_days: int,
    attempts_per_sha: int,
) -> dict[str, int]:
    """Aplica retenção lock-aware sem remover evidência ativa ou referenciada.

    Um SHA inteiro é primeiro renomeado atomicamente para um nome de quarentena
    enquanto seu lock ainda está detido. O lock é então liberado e a quarentena
    removida. Uma nova execução do mesmo SHA pode recriar o namespace original
    sem compartilhar inode/diretório com a árvore em descarte.
    """
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
        # Captura mtime ANTES de tocar .lock para evitar alterar o timestamp usado na comparação
        sha_root_mtime = sha_root.stat().st_mtime
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
            if sha_root.name not in keep_by_count and sha_root_mtime < cutoff:
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
            stats["removed_shas"] += 1
    return stats


def _parser() -> argparse.ArgumentParser:
    """Constrói parser de linha de comando sem executar efeitos colaterais."""
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
    """Executa subcomandos e converte erros de contrato em exit code 2."""
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
