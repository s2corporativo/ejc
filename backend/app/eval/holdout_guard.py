from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def inspect_holdout(path: str | Path, repo_root: str | Path | None = None) -> dict:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(p)
    root = Path(repo_root or Path(__file__).resolve().parents[3]).resolve()

    tracked = False
    try:
        rel = p.relative_to(root)
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--error-unmatch", str(rel)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        tracked = proc.returncode == 0
    except ValueError:
        rel = None

    rows = 0
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip() and not line.lstrip().startswith("#"):
                json.loads(line)
                rows += 1

    return {
        "path": str(p),
        "inside_repo": rel is not None,
        "tracked_by_git": tracked,
        "cases": rows,
        "sha256": _sha256(p),
        "safe_for_secret_holdout": not tracked,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Valida holdout jurídico secreto sem expor conteúdo")
    ap.add_argument("path")
    ap.add_argument("--manifest")
    args = ap.parse_args(argv)
    report = inspect_holdout(args.path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.manifest:
        Path(args.manifest).write_text(
            json.dumps({k: v for k, v in report.items() if k != "path"}, indent=2),
            encoding="utf-8",
        )
    return 0 if report["safe_for_secret_holdout"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
