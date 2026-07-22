#!/usr/bin/env python3
"""Classifica migrations Alembic pendentes para deploy com rollback de imagem.

O rollback automático restaura containers/imagens, não o schema. Por isso o
classificador aprova automaticamente apenas mudanças *expand-only* compatíveis
com a versão anterior da aplicação. Somente ``upgrade()`` é analisado;
``downgrade()`` não participa da decisão de implantação.
"""
from __future__ import annotations

import argparse
import ast
import json
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
        if isinstance(item, (ast.Assign, ast.AnnAssign)):
            targets = item.targets if isinstance(item, ast.Assign) else [item.target]
            value = item.value
            for target in targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return _literal(value)
    return None


def _load_revisions(directory: Path) -> dict[str, Revision]:
    if not directory.is_dir():
        raise RuntimeError(f"diretório de migrations inexistente: {directory}")

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
            isinstance(value, str) and value for value in down
        ):
            down_revisions = tuple(down)
        else:
            raise RuntimeError(f"down_revision dinâmico não suportado: {path}")
        if revision in revisions:
            raise RuntimeError(f"revision duplicada: {revision}")
        revisions[revision] = Revision(revision, down_revisions, path)

    if not revisions:
        raise RuntimeError("nenhuma migration Alembic encontrada")

    for item in revisions.values():
        for parent in item.down_revisions:
            if parent not in revisions:
                raise RuntimeError(
                    f"down_revision inexistente: {item.revision} -> {parent}"
                )
        if len(item.down_revisions) > 1:
            raise RuntimeError(
                f"merge revision exige revisão humana: {item.revision}"
            )
    return revisions


def _linear_pending_path(
    revisions: dict[str, Revision], current_revision: str
) -> tuple[str, list[Revision]]:
    if current_revision not in revisions:
        raise RuntimeError(
            f"revision atual não existe no código: {current_revision}"
        )

    children: dict[str, list[str]] = {revision: [] for revision in revisions}
    for item in revisions.values():
        for parent in item.down_revisions:
            children[parent].append(item.revision)

    heads = sorted(
        revision for revision, descendants in children.items() if not descendants
    )
    if len(heads) != 1:
        raise RuntimeError(f"esperado head único; encontrados: {heads}")
    head = heads[0]

    pending: list[Revision] = []
    cursor = current_revision
    seen: set[str] = set()
    while cursor != head:
        if cursor in seen:
            raise RuntimeError(f"ciclo no grafo Alembic em {cursor}")
        seen.add(cursor)
        next_items = sorted(children.get(cursor, []))
        if len(next_items) != 1:
            raise RuntimeError(
                f"caminho não linear a partir de {cursor}: {next_items}"
            )
        cursor = next_items[0]
        pending.append(revisions[cursor])

    return head, pending


def _upgrade_function(tree: ast.Module, path: Path) -> ast.FunctionDef:
    matches = [
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == "upgrade"
    ]
    if len(matches) != 1:
        raise RuntimeError(f"upgrade() ausente ou duplicado: {path}")
    return matches[0]


def _op_call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        if func.value.id == "op":
            return func.attr
    return None


def _attribute_call_name(node: ast.Call) -> str | None:
    return node.func.attr if isinstance(node.func, ast.Attribute) else None


def _keyword_literal(call: ast.Call, name: str):
    for keyword in call.keywords:
        if keyword.arg == name:
            return _literal(keyword.value)
    return None


def _column_is_expand_only(call: ast.Call) -> tuple[bool, str]:
    if len(call.args) < 2 or not isinstance(call.args[1], ast.Call):
        return False, "add_column sem Column estática"
    column = call.args[1]
    nullable = _keyword_literal(column, "nullable")
    server_default_present = any(
        keyword.arg == "server_default"
        and not (
            isinstance(keyword.value, ast.Constant)
            and keyword.value.value is None
        )
        for keyword in column.keywords
    )
    if nullable is False and not server_default_present:
        return False, "coluna NOT NULL sem server_default"
    return True, ""


def _classify(revision: Revision) -> list[str]:
    tree = ast.parse(
        revision.path.read_text(encoding="utf-8"),
        filename=str(revision.path),
    )
    upgrade = _upgrade_function(tree, revision.path)
    findings: list[str] = []
    allowed = {
        "create_table",
        "create_index",
        "create_foreign_key",
        "create_check_constraint",
        "add_column",
    }
    review_required = {
        "drop_table",
        "drop_column",
        "drop_index",
        "drop_constraint",
        "alter_column",
        "rename_table",
        "execute",
        "batch_alter_table",
        "create_unique_constraint",
        "get_bind",
    }

    for node in ast.walk(upgrade):
        if not isinstance(node, ast.Call):
            continue
        line = getattr(node, "lineno", 0)
        op_name = _op_call_name(node)
        attr_name = _attribute_call_name(node)

        if op_name is None and attr_name == "execute":
            findings.append(f"linha {line}: chamada .execute exige revisão")
            continue
        if op_name is None:
            continue

        if op_name == "add_column":
            ok, reason = _column_is_expand_only(node)
            if not ok:
                findings.append(f"linha {line}: {reason}")
        elif op_name == "create_index":
            if _keyword_literal(node, "unique") is True:
                findings.append(
                    f"linha {line}: índice UNIQUE exige revisão de dados/lock"
                )
        elif op_name in review_required:
            findings.append(f"linha {line}: op.{op_name} exige revisão")
        elif op_name not in allowed:
            findings.append(f"linha {line}: op.{op_name} não está na allowlist")

    return findings


def evaluate(directory: Path, current_revision: str) -> dict[str, object]:
    revisions = _load_revisions(directory)
    target, pending = _linear_pending_path(revisions, current_revision)
    migrations: list[dict[str, object]] = []
    for revision in pending:
        reasons = _classify(revision)
        migrations.append(
            {
                "revision": revision.revision,
                "file": revision.path.name,
                "compatible": not reasons,
                "reasons": reasons,
            }
        )
    return {
        "current_revision": current_revision,
        "target_revision": target,
        "pending_count": len(pending),
        "compatible": all(item["compatible"] for item in migrations),
        "migrations": migrations,
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
