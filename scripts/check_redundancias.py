#!/usr/bin/env python3
"""Reprova novas cópias literais; relatório contém apenas hashes e localização.

Compara blocos de 12 linhas substanciais com um commit imutável. Não substitui
o inventário semântico e não executa arquivos analisados ou altera a árvore.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tokenize

BASE_REF = "1fd771af3ba27780e93d49cb908b57bb7b0b2acf"
ROOTS = ("backend/app", "backend/scripts", "frontend/src", "frontend/scripts", "scripts")
EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".mjs", ".css", ".sh"}
WINDOW = 12


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.DEVNULL)


def groups(files):
    found = defaultdict(list)
    for name, content in sorted(files.items()):
        lines = content.splitlines()
        if name.endswith(".py"):
            # Tokenização reconhece comentários sem remover '#' de strings.
            for token in tokenize.generate_tokens(io.StringIO(content).readline):
                if token.type == tokenize.COMMENT:
                    lines[token.start[0] - 1] = lines[token.start[0] - 1][:token.start[1]]
        substantial = [(i + 1, line.strip()) for i, line in enumerate(lines)
                       if len(line.strip()) >= 10 and not line.strip().startswith(("#", "//"))]
        for index in range(len(substantial) - WINDOW + 1):
            block = substantial[index:index + WINDOW]
            digest = hashlib.sha256("\n".join(line for _, line in block).encode()).hexdigest()
            found[digest].append({"path": name, "line": block[0][0]})
    return {digest: places for digest, places in found.items() if len(places) > 1}


def sources(root, ref=None):
    args = ("ls-tree", "-rz", "--name-only", ref, "--", *ROOTS) if ref else (
        "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *ROOTS,
    )
    result = {}
    for name in sorted(set(git(root, *args).decode().strip("\0").split("\0"))):
        path = root / name
        if not name or path.suffix not in EXTENSIONS:
            continue
        if ref:
            mode = git(root, "ls-tree", ref, "--", name).decode().split()[0]
            if mode == "120000":  # aliases deliberados não contam como cópia
                continue
            content = git(root, "show", f"{ref}:{name}")
        else:
            if path.is_symlink() or not path.is_file():
                continue
            content = path.read_bytes()
        result[name] = content.decode("utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--base-ref", default=BASE_REF)
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        base = git(root, "rev-parse", "--verify", args.base_ref + "^{commit}").decode().strip()
        baseline = groups(sources(root, base))
        current_sources = sources(root)
        current = groups(current_sources)
        findings = [{"sha256": digest, "occurrences": places,
                     "baseline_occurrences": len(baseline.get(digest, []))}
                    for digest, places in sorted(current.items())
                    if len(places) > len(baseline.get(digest, []))]
        print(json.dumps({"base_commit": base, "window_lines": WINDOW,
                          "files": len(current_sources), "baseline_groups": len(baseline),
                          "new_groups": len(findings), "findings": findings[:20],
                          "findings_truncated": len(findings) > 20}, ensure_ascii=False, indent=2))
        return int(bool(findings))
    except (OSError, ValueError, SyntaxError, tokenize.TokenError, subprocess.CalledProcessError):
        print("Guard indisponível: confira referência Git, codificação e tokenização dos fontes.", flush=True)
        return 2  # não imprime conteúdo sensível nem produz um falso verde


if __name__ == "__main__":
    raise SystemExit(main())
