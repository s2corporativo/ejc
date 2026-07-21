#!/usr/bin/env python3
"""Classifica migrations Alembic pendentes quanto à retrocompatibilidade.

Uso:
    python scripts/check_migration_compatibility.py \
        --versions-dir backend/alembic/versions \
        --current-revision 112_client_pii_drop_plaintext

Saída JSON e exit code:
- 0: nenhuma migration pendente ou todas retrocompatíveis;
- 1: migration pendente exige revisão/override humano;
- 2: grafo/revisão inválidos.

A política é deliberadamente conservadora. O rollback automático restaura imagens,
não schema; portanto, só operações expand-only são aprovadas automaticamente.
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Revision:
    revision: str
    down_revisions: tuple[str, ...]
    path: Path


def _literal(node: ast.AST | None):
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None


def _assignment(tree: ast.Module, name: str):
    for item in tree.body:
        if isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return _literal(item.value)
    return None


def _load_revisions(directory: Path) -> dict[str, Revision]:
    revisions: dict[str, Revision] = {}
    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("__"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        revision = _assignment(tree, "revision")
        down = _assignment(tree, "down_revision")
        if not isinstance(revision, str) or not revision:
            continue
        if down is None:
            down_revisions: tuple[str, ...] = ()
        elif isinstance(down, str):
            down_revisions = (down,)
        elif isinstance(down, (tuple, list)) and all(
            isinstance(value, str) for value in down
        ):
            down_revisions = tuple(down)
        else:
            raise RuntimeError(f"down_revision dinâmico não suportado: {path}")
        if revision in revisions:
            raise RuntimeError(f"revision duplicada: {revision}")
        revisions[revision] = Revision(revision, down_revisions, path)
    if not revisions:
        raise RuntimeError("nenhuma migration Alembic encontrada")
    return revisions


def _pending_path(
    revisions: dict[str, Revision],
    current_revision: str,
) -> list[Revision]:
    if current_revision not in revisions:
        raise RuntimeError(
            f"revision atual não existe no código: {current_revision}"
        )

    children: dict[str, list[str]] = {revision: [] for revision in revisions}
    for item in revisions.values():
        for parent in item.down_revisions:
            if parent in children:
                children[parent].append(item.revision)

    heads = sorted(
        revision for revision, descendants in children.items() if not descendants
    )
    if len(heads) != 1:
        raise RuntimeError(f"esperado head único; encontrados: {heads}")
    target = heads[0]
    if current_revision == target:
        return []

    path: list[str] = []

    def visit(revision: str, seen: set[str]) -> bool:
        if revision in seen:
            return False
        if revision == target:
            return True
        next_seen = {*seen, revision}
        for child in sorted(children.get(revision, [])):
            path.append(child)
            if visit(child, next_seen):
                return True
            path.pop()
        return False

    if not visit(current_revision, set()):
        raise RuntimeError(
            f"não há caminho linear da revisão {current_revision} até {target}"
        )
    return [revisions[revision] for revision in path]


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        if func.value.id == "op":
            return func.attr
    return None


def _column_is_expand_only(call: ast.Call) -> tuple[bool, str]:
    # op.add_column("table", sa.Column(...))
    if len(call.args) < 2 or not isinstance(call.args[1], ast.Call):
        return False, "add_column sem Column estática"
    column = call.args[1]
    nullable = None
    has_server_default = False
    for keyword in column.keywords:
        if keyword.arg == "nullable":
            nullable = _literal(keyword.value)
        elif keyword.arg == "server_default":
            has_server_default = True
    if nullable is False and not has_server_default:
        return False, "coluna NOT NULL sem server_default"
    return True, ""


def _classify(revision: Revision) -> list[str]:
    tree = ast.parse(
        revision.path.read_text(encoding="utf-8"),
        filename=str(revision.path),
    )
    forbidden: list[str] = []
    allowed = {
        "create_table",
        "create_index",
        "create_foreign_key",
        "create_check_constraint",
        "add_column",
    }
    explicitly_destructive = {
        "drop_table",
        "drop_column",
        "drop_index",
        "drop_constraint",
        "alter_column",
        "rename_table",
        "execute",
        "batch_alter_table",
        "create_unique_constraint",
    }

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if not name:
            continue
        line = getattr(node, "lineno", 0)
        if name == "add_column":
            ok, reason = _column_is_expand_only(node)
            if not ok:
                forbidden.append(f"linha {line}: {reason}")
        elif name in explicitly_destructive:
            forbidden.append(f"linha {line}: op.{name} exige revisão")
        elif name not in allowed:
            forbidden.append(f"linha {line}: op.{name} não está na allowlist")
    return forbidden


def evaluate(directory: Path, current_revision: str) -> dict[str, object]:
    revisions = _load_revisions(directory)
    pending = _pending_path(revisions, current_revision)
    findings: list[dict[str, object]] = []
    for revision in pending:
        reasons = _classify(revision)
        findings.append(
            {
                "revision": revision.revision,
                "file": revision.path.name,
                "compatible": not reasons,
                "reasons": reasons,
            }
        )
    return {
        "current_revision": current_revision,
        "target_revision": next(
            revision
            for revision in revisions
            if not any(
                revision in item.down_revisions for item in revisions.values()
            )
        ),
        "pending_count": len(pending),
        "compatible": all(item["compatible"] for item in findings),
        "migrations": findings,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--versions-dir", type=Path, required=True)
    parser.add_argument("--current-revision", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        result = evaluate(args.versions_dir, args.current_revision.strip())
        exit_code = 0 if result["compatible"] else 1
    except Exception as exc:
        result = {
            "compatible": False,
            "error": f"{type(exc).__name__}: {str(exc)[:500]}",
        }
        exit_code = 2

    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
