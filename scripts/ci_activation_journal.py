#!/usr/bin/env python3
"""Journal durável da ativação/desativação do fallback local de CI.

O arquivo fica fora do repositório, contém somente metadados operacionais e usa
escrita atômica + fsync para permitir recovery após SIGKILL/reboot/power loss.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import tempfile
from pathlib import Path

PHASES = (
    "starting",
    "draining",
    "watcher",
    "hooks",
    "protection",
    "commit",
    "active",
)


def _fail(message: str) -> "NoReturn":
    raise SystemExit(message)


def _assert_safe_root(root: Path) -> Path:
    if not root.is_absolute():
        _fail("state root deve ser absoluto")
    current = Path(root.anchor)
    for part in root.parts[1:]:
        current = current / part
        if current.exists() or current.is_symlink():
            st = os.lstat(current)
            if stat.S_ISLNK(st.st_mode):
                _fail("state root contém componente symlink")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    st = os.stat(root, follow_symlinks=False)
    if not stat.S_ISDIR(st.st_mode):
        _fail("state root não é diretório")
    if st.st_uid != os.getuid():
        _fail("state root não pertence ao usuário atual")
    if stat.S_IMODE(st.st_mode) & 0o077:
        _fail("state root deve ser 0700")
    return root.resolve(strict=True)


def _assert_safe_file(root: Path, path: Path, *, allow_missing: bool) -> None:
    if not path.is_absolute():
        _fail("journal deve usar caminho absoluto")
    parent = path.parent.resolve(strict=True)
    try:
        parent.relative_to(root)
    except ValueError:
        _fail("journal deve permanecer sob state root")
    if not path.exists() and not path.is_symlink():
        if allow_missing:
            return
        _fail("journal ausente")
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        _fail("journal deve ser arquivo regular sem symlink")
    if st.st_uid != os.getuid() or st.st_nlink != 1:
        _fail("journal possui ownership/link count inseguro")
    if stat.S_IMODE(st.st_mode) != 0o600:
        _fail("journal deve ser 0600")


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _load(root: Path, path: Path) -> dict:
    _assert_safe_file(root, path, allow_missing=False)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"journal inválido: {type(exc).__name__}")
    if data.get("schema") != 1 or data.get("phase") not in PHASES:
        _fail("journal possui schema/fase inválidos")
    for key in ("repo", "state_root", "protection_backup", "hooks_backup"):
        if not isinstance(data.get(key), str):
            _fail(f"journal sem campo válido: {key}")
    if Path(data["state_root"]).resolve(strict=False) != root:
        _fail("journal pertence a outro state root")
    return data


def _atomic_write(root: Path, path: Path, payload: dict) -> None:
    _assert_safe_file(root, path, allow_missing=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
        with os.fdopen(fd, "wb", closefd=True) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600, follow_symlinks=False)
        _fsync_dir(path.parent)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def cmd_begin(args: argparse.Namespace) -> None:
    root = _assert_safe_root(Path(args.state_root))
    path = Path(args.file)
    _assert_safe_file(root, path, allow_missing=True)
    if path.exists() or path.is_symlink():
        _fail("journal incompleto já existe; recovery obrigatório")
    payload = {
        "schema": 1,
        "phase": "starting",
        "repo": args.repo,
        "state_root": str(root),
        "protection_backup": args.protection_backup,
        "hooks_backup": args.hooks_backup,
        "scheduler": args.scheduler,
    }
    _atomic_write(root, path, payload)


def cmd_phase(args: argparse.Namespace) -> None:
    root = _assert_safe_root(Path(args.state_root))
    path = Path(args.file)
    data = _load(root, path)
    old = PHASES.index(data["phase"])
    new = PHASES.index(args.phase)
    if new < old:
        _fail("journal não permite regressão de fase")
    data["phase"] = args.phase
    _atomic_write(root, path, data)


def cmd_show(args: argparse.Namespace) -> None:
    root = _assert_safe_root(Path(args.state_root))
    path = Path(args.file)
    data = _load(root, path)
    print(json.dumps(data, sort_keys=True))


def cmd_clear(args: argparse.Namespace) -> None:
    root = _assert_safe_root(Path(args.state_root))
    path = Path(args.file)
    _load(root, path)
    path.unlink()
    _fsync_dir(path.parent)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("begin", "phase", "show", "clear"):
        sp = sub.add_parser(name)
        sp.add_argument("--state-root", required=True)
        sp.add_argument("--file", required=True)
    begin = sub.choices["begin"]
    begin.add_argument("--repo", required=True)
    begin.add_argument("--protection-backup", required=True)
    begin.add_argument("--hooks-backup", required=True)
    begin.add_argument("--scheduler", required=True)
    phase = sub.choices["phase"]
    phase.add_argument("--phase", required=True, choices=PHASES)
    return p


def main() -> None:
    args = parser().parse_args()
    {"begin": cmd_begin, "phase": cmd_phase, "show": cmd_show, "clear": cmd_clear}[args.command](args)


if __name__ == "__main__":
    main()
