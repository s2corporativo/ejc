#!/usr/bin/env python3
"""Seleciona testes diretamente afetados para o gate rápido de PR.

Não substitui a suíte integral de release/main. A seleção é conservadora e
sempre inclui contratos basais por stack.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

MAX_SELECTED = 30

BACKEND_BASELINE = (
    "tests/test_alembic_single_head.py",
    "tests/test_rotas_registro_explicito.py",
)
FRONTEND_BASELINE = (
    "src/config/canonicalNavigation.test.ts",
)


def _existing(root: Path, paths: set[str]) -> list[str]:
    return sorted(p for p in paths if (root / p).is_file())


def select_backend(repo: Path, changed: list[str]) -> list[str]:
    root = repo / "backend"
    selected = set(BACKEND_BASELINE)
    tests = list((root / "tests").glob("test_*.py")) if (root / "tests").exists() else []

    for rel in changed:
        p = Path(rel)
        if rel.startswith("backend/tests/") and p.suffix == ".py":
            selected.add(p.relative_to("backend").as_posix())
            continue
        if not rel.startswith("backend/") or p.suffix != ".py":
            continue

        stem = p.stem
        module_token = rel.removeprefix("backend/").removesuffix(".py").replace("/", ".")
        for test in tests:
            name = test.name.lower()
            if stem.lower() in name:
                selected.add(test.relative_to(root).as_posix())
                continue
            try:
                content = test.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if module_token in content:
                selected.add(test.relative_to(root).as_posix())

        if rel.startswith("backend/alembic/"):
            selected.update({
                "tests/test_migration_reservations_head.py",
                "tests/test_migrations_reais_passam_no_gate.py",
                "tests/test_schema_dr_parity.py",
            })

    existing = _existing(root, selected)
    return existing[:MAX_SELECTED]


def select_frontend(repo: Path, changed: list[str]) -> list[str]:
    root = repo / "frontend"
    selected = set(FRONTEND_BASELINE)
    tests = list((root / "src").rglob("*.test.ts")) + list((root / "src").rglob("*.test.tsx"))

    for rel in changed:
        p = Path(rel)
        if rel.startswith("frontend/src/") and ".test." in p.name:
            selected.add(p.relative_to("frontend").as_posix())
            continue
        if not rel.startswith("frontend/src/") or p.suffix not in {".ts", ".tsx", ".css"}:
            continue

        stem = p.stem.replace(".module", "")
        for test in tests:
            if stem.lower() in test.name.lower():
                selected.add(test.relative_to(root).as_posix())

        if rel in {"frontend/src/App.tsx", "frontend/src/config/moduleRegistry.tsx"} or rel.startswith("frontend/src/config/"):
            selected.add("src/config/canonicalNavigation.test.ts")
        if "Dashboard" in rel or "ejc-dashboard" in rel or "ejc-tokens.css" in rel:
            selected.add("src/pages/DashboardUltra.test.tsx")

    existing = _existing(root, selected)
    return existing[:MAX_SELECTED]


def changed_paths(repo: Path, base: str) -> list[str]:
    command = ["git", "diff", "--name-only", "--diff-filter=ACMR", f"{base}...HEAD"]
    proc = subprocess.run(
        command,
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0 and "no merge base" in proc.stderr.lower():
        # Woodpecker pode entregar PR merge commits em checkout raso. Nesse
        # cenário os dois commits existem, mas o ancestral comum está fora da
        # profundidade clonada. O diff de duas pontas preserva a seleção
        # conservadora sem exigir unshallow do repositório inteiro.
        proc = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMR", base, "HEAD"],
            cwd=repo,
            text=True,
            capture_output=True,
            check=False,
        )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git diff falhou")
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stack", choices=("backend", "frontend"), required=True)
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--repo", default=".")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    changed = changed_paths(repo, args.base)
    selected = (
        select_backend(repo, changed)
        if args.stack == "backend"
        else select_frontend(repo, changed)
    )
    for item in selected:
        print(item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
