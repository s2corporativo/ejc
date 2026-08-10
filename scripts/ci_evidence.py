#!/usr/bin/env python3
"""Gerencia a evidência local imutável do fallback de CI do EJC.

Este módulo não acessa GitHub e não executa a suíte. Sua única responsabilidade é
modelar tentativas por SHA como uma máquina de estados fail-closed:

1. ``start`` cria uma tentativa nova e a torna imediatamente a tentativa atual;
2. ``finish`` finaliza somente a tentativa atual;
3. apenas uma tentativa atual, completa e bem-sucedida pode virar ``latest-success``;
4. ``verify`` aceita sucesso somente quando ele pertence à tentativa atual e todos
   os oito logs obrigatórios continuam byte-a-byte íntegros.

Isso elimina o caso perigoso ``sucesso A -> tentativa B falha -> reutilizar A``.
A criação de B invalida semanticamente A antes mesmo de B produzir seu primeiro log.

Complexidade
------------
A criação/ponteiros é O(1). Finalização e verificação são O(B) em tempo, onde B é
o total de bytes dos oito logs, e O(1) em memória adicional: hashing é feito em
blocos fixos de 1 MiB, sem carregar logs inteiros em RAM.
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
    """Retorna timestamp UTC ISO-8601 com timezone explícito."""

    return datetime.now(timezone.utc).isoformat()


def _validate_sha(value: str) -> str:
    """Valida um SHA-1 Git completo em hexadecimal minúsculo."""

    if len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError("SHA deve conter exatamente 40 caracteres hexadecimais minúsculos")
    return value


def _hash_file(path: pathlib.Path) -> tuple[str, int]:
    """Calcula SHA-256 e tamanho do arquivo em streaming O(1) memória."""

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
    """Persiste a entrada de diretório após ``os.replace`` quando suportado."""

    try:
        fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    """Grava JSON 0600 por replace atômico e fsync de arquivo + diretório."""

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
    """Lê objeto JSON regular; symlink e tipos JSON não-objeto são rejeitados."""

    if path.is_symlink() or not path.is_file():
        raise ValueError(f"arquivo JSON inválido: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON precisa ser objeto: {path}")
    return value


def _resolve_child(base: pathlib.Path, relative: str) -> pathlib.Path:
    """Resolve filho relativo sem aceitar path traversal ou caminho absoluto."""

    rel = pathlib.PurePosixPath(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("caminho relativo inseguro")
    resolved_base = base.resolve()
    resolved = (resolved_base / pathlib.Path(*rel.parts)).resolve()
    if resolved != resolved_base and resolved_base not in resolved.parents:
        raise ValueError("caminho escapou da raiz de evidência")
    return resolved


def _attempts_root(sha_root: pathlib.Path) -> pathlib.Path:
    """Retorna a raiz canônica de tentativas do SHA."""

    return (sha_root.resolve() / "attempts").resolve()


def _resolve_current_attempt(sha_root: pathlib.Path, sha: str) -> pathlib.Path:
    """Resolve a tentativa atual a partir de ``latest-attempt.json``."""

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


def start_attempt(
    root: pathlib.Path, sha: str, ref: str, pr: int | None
) -> pathlib.Path:
    """Cria tentativa isolada e invalida semanticamente qualquer sucesso anterior.

    A invalidação não exige apagar ``latest-success``: ``verify_success`` exige que
    o ponteiro de sucesso pertença à mesma tentativa apontada por
    ``latest-attempt``. Portanto, publicar uma nova tentativa torna todo verde
    anterior não-promovível de forma atômica.
    """

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
    """Finaliza exclusivamente a tentativa atual e opcionalmente promove sucesso.

    Sucesso promovível exige exit code zero e exatamente os oito logs do full gate.
    Uma tentativa que deixou de ser a atual não pode finalizar/promover depois que
    outra começou, fechando corrida entre executores.
    """

    sha = _validate_sha(sha)
    attempt = attempt.resolve()
    sha_root = sha_root.resolve()
    attempts_root = _attempts_root(sha_root)
    if attempts_root not in attempt.parents or attempt.is_symlink() or not attempt.is_dir():
        raise ValueError("tentativa fora da raiz de evidência")
    current_attempt = _resolve_current_attempt(sha_root, sha)
    if attempt != current_attempt:
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
            f"sucesso exige exatamente os oito logs do full gate; missing={missing}, extra={extra}"
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
    """Valida o sucesso atual, sua proveniência e todos os logs obrigatórios."""

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


def latest_log(
    sha_root: pathlib.Path, sha: str, started_epoch: int
) -> pathlib.Path | None:
    """Retorna o log relevante da tentativa atual para classificar infraestrutura.

    Quando a tentativa já possui summary de falha, o log do ``failed_stage`` tem
    precedência. Durante uma tentativa ainda em andamento, usa o log mais recente
    com mtime igual ou posterior ao início informado.
    """

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


def _parser() -> argparse.ArgumentParser:
    """Constrói a CLI estável consumida pelos scripts Bash do fallback."""

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
    """Executa a suboperação solicitada e traduz erros esperados para exit code 2."""

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
