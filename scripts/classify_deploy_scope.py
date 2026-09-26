#!/usr/bin/env python3
"""Classifica o menor escopo seguro de deploy entre dois commits.

Fail-closed: somente retorna "frontend" quando TODOS os paths alterados estão
sob frontend/. Qualquer erro, histórico não linear, SHA ausente ou arquivo
fora dessa árvore retorna "full".

O classificador não autoriza deploy; Woodpecker, migration gate, mutex, backup,
healthchecks e rollback continuam sendo gates independentes.
"""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def classify(repo: Path, previous: str, target: str) -> str:
    if not SHA_RE.fullmatch(previous) or not SHA_RE.fullmatch(target):
        return "full"
    if previous == target:
        return "full"

    for sha in (previous, target):
        if _git(repo, "cat-file", "-e", f"{sha}^{{commit}}").returncode != 0:
            return "full"

    if _git(repo, "merge-base", "--is-ancestor", previous, target).returncode != 0:
        return "full"

    diff = _git(repo, "diff", "--name-only", "--no-renames", previous, target)
    if diff.returncode != 0:
        return "full"
    paths = [line.strip() for line in diff.stdout.splitlines() if line.strip()]
    if not paths:
        return "full"
    return "frontend" if all(path.startswith("frontend/") for path in paths) else "full"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--previous", required=True)
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    print(classify(Path(args.repo), args.previous, args.target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
