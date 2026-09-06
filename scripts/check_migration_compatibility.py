#!/usr/bin/env python3
"""Classifica migrations Alembic para deploy com rollback de imagens.

O rollback automático restaura containers, não o schema. O classificador aprova
somente operações expand-only ou backfills aditivos explicitamente declarados,
com SQL literal, targets allowlisted e idempotência verificável. ``downgrade()``
não participa da decisão de implantação.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ADDITIVE_DATA_BACKFILL = "additive_data_backfill"
HUMAN_REVIEWED_DROP = "human_reviewed_drop"

# DB-08 (auditoria de camadas 06/09/2026): ``create_foreign_key`` e
# ``create_check_constraint`` em tabela EXISTENTE validam a tabela inteira sob
# lock (SHARE ROW EXCLUSIVE) no ``ALTER TABLE`` — não são expand-only. Passam
# a exigir ``postgresql_not_valid=True`` (Alembic emite ``NOT VALID``; a
# validação vai para migration separada) ou tabela criada no mesmo
# ``upgrade()`` (vazia — nada a varrer). Catraca por número de arquivo: as
# revisões 152 e 153 já mesclaram FK sem NOT VALID e não se reescreve migration
# aplicada; a partir da 158 a regra vale.
NOT_VALID_OBRIGATORIO_A_PARTIR_DE = 158
_CONSTRAINTS_COM_VALIDACAO = {"create_foreign_key", "create_check_constraint"}
_FORBIDDEN_SQL = {
    "ALTER",
    "CALL",
    "COPY",
    "CREATE",
    "DELETE",
    "DROP",
    "GRANT",
    "LOCK",
    "MERGE",
    "REVOKE",
    "SET",
    "TRUNCATE",
    "UPDATE",
    "VACUUM",
}


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
            for target in targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return _literal(item.value)
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

    for item in pending:
        if len(item.down_revisions) > 1:
            raise RuntimeError(
                f"merge revision exige revisão humana: {item.revision}"
            )

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


def _alter_column_is_expand_only(call: ast.Call) -> tuple[bool, str]:
    """Aprova ``op.alter_column`` somente quando ``type_`` for widening
    estrita e estática em relação a ``existing_type`` (ex.: String(10)→
    String(15)). Retorna (False, motivo) em qualquer outro caso."""
    type_ = None
    existing = None
    for keyword in call.keywords:
        if keyword.arg == "type_":
            type_ = keyword.value
        elif keyword.arg == "existing_type":
            existing = keyword.value
    if not isinstance(type_, ast.Call) or not isinstance(existing, ast.Call):
        return False, "alter_column sem type_/existing_type estáticos"
    name = _type_name(type_.func)
    if name is None or name not in {"String", "Integer", "BigInteger", "Numeric"}:
        return False, f"alter_column com tipo {name} fora do padrão de widening"
    t_args = [a for a in type_.args if isinstance(a, ast.Constant)]
    e_args = [a for a in existing.args if isinstance(a, ast.Constant)]
    if not (t_args and e_args):
        return False, "alter_column sem tamanho estático comparável"
    try:
        t_size = int(t_args[0].value)
        e_size = int(e_args[0].value)
    except (TypeError, ValueError):
        return False, "alter_column com tamanho não numérico"
    if name == "Numeric":
        # Numeric(precision, scale): exige precision maior E scale igual
        t_scale = int(t_args[1].value) if len(t_args) > 1 else 0
        e_scale = int(e_args[1].value) if len(e_args) > 1 else 0
        if not (t_size > e_size and t_scale == e_scale):
            return False, "alter_column Numeric sem widening estrita"
        return True, ""
    if t_size <= e_size:
        return False, f"alter_column sem widening estrita ({e_size}→{t_size})"
    return True, ""


def _type_name(func: ast.AST) -> str | None:
    """Resolve ``String`` de ``sa.String(...)`` ou ``String(...)``."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return func.attr
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


def _extract_string_from_call(call: ast.Call) -> str | None:
    """Extract the first string argument from a function call."""
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        return call.args[0].value
    return None


_DDL_KEYWORDS_SAFE = {
    "CREATE TYPE",
    "CREATE INDEX",
}


def _is_safe_expand_ddl(sql: str) -> bool:
    """Return True if SQL is a known-safe DDL pattern for expand_only."""
    upper = sql.upper().strip()
    # DO $$ BEGIN CREATE TYPE ... EXCEPTION WHEN DUPLICATE_OBJECT THEN NULL; END $$
    if "CREATE TYPE" in upper and "EXCEPTION WHEN DUPLICATE_OBJECT" in upper:
        return True
    # CREATE TYPE IF NOT EXISTS
    if re.match(r"\s*CREATE\s+TYPE\s+\w+\s+IF\s+NOT\s+EXISTS\b", upper):
        return True
    # CREATE INDEX IF NOT EXISTS
    if re.match(r"\s*CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\b", upper):
        return True
    # ALTER TABLE t ADD CONSTRAINT c CHECK (...) NOT VALID  /  FOREIGN KEY ... NOT VALID
    # (DB-08): constraint declarada sem varrer a tabela — expand-only.
    if re.match(
        r"\s*ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?[\w.\"]+\s+ADD\s+CONSTRAINT\s+[\w\"]+\s+"
        r"(?:CHECK|FOREIGN\s+KEY)\b[\s\S]*\bNOT\s+VALID\s*;?\s*$",
        upper,
    ):
        return True
    return False


def _static_upgrade_shape_findings(upgrade: ast.FunctionDef) -> list[str]:
    """Exige operações ``op.*`` diretas no corpo de ``upgrade()``."""
    findings: list[str] = []
    for statement in upgrade.body:
        line = getattr(statement, "lineno", 0)
        if isinstance(statement, ast.Pass):
            continue
        if (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            continue
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
            if _op_call_name(statement.value) is None:
                findings.append(
                    f"linha {line}: chamada fora de op.* exige revisão humana"
                )
            continue
        findings.append(
            f"linha {line}: estrutura dinâmica {type(statement).__name__} "
            "exige revisão humana"
        )
    return findings


def _declared_backfill_targets(tree: ast.Module) -> tuple[str, ...] | None:
    raw = _assignment(tree, "data_backfill_targets")
    if not isinstance(raw, (tuple, list)) or not raw:
        return None
    if not all(isinstance(item, str) and re.fullmatch(r"[a-z_][a-z0-9_]*", item) for item in raw):
        return None
    if len(set(raw)) != len(raw):
        return None
    return tuple(raw)


def _strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", sql)


def _safe_backfill_sql_findings(
    call: ast.Call,
    declared_targets: tuple[str, ...] | None,
) -> tuple[list[str], set[str]]:
    line = getattr(call, "lineno", 0)
    findings: list[str] = []
    used_targets: set[str] = set()
    if declared_targets is None:
        return [f"linha {line}: data_backfill_targets ausente ou inválido"], used_targets
    if len(call.args) != 1 or call.keywords:
        return [f"linha {line}: backfill exige um único argumento SQL literal"], used_targets
    sql = _literal(call.args[0])
    if not isinstance(sql, str) or not sql.strip():
        return [f"linha {line}: SQL de backfill não é string literal"], used_targets

    cleaned = _strip_sql_comments(sql)
    upper = cleaned.upper()

    # DDL operations (CREATE TYPE via DO $$) — safe, not a backfill concern
    if _is_safe_expand_ddl(sql):
        return findings, used_targets

    # UPDATE ... WHERE — targeted, idempotent backfill
    if re.match(r"\s*UPDATE\s+\w+\s+SET\b", upper) and "WHERE" in upper:
        table_match = re.match(r"\s*UPDATE\s+(\w+)\s+SET\b", upper)
        if table_match:
            used_targets = {table_match.group(1).lower()}
            undeclared = used_targets - set(declared_targets)
            if undeclared:
                findings.append(
                    f"linha {line}: target fora da allowlist: {', '.join(sorted(undeclared))}"
                )
        return findings, used_targets

    forbidden = sorted(
        keyword
        for keyword in _FORBIDDEN_SQL
        if re.search(rf"\b{keyword}\b", upper)
    )
    if forbidden:
        findings.append(
            f"linha {line}: SQL aditivo contém verbo proibido: {', '.join(forbidden)}"
        )

    inserts = re.findall(
        r"\bINSERT\s+INTO\s+(?:PUBLIC\.)?([A-Z_][A-Z0-9_]*)\b",
        upper,
    )
    if not inserts:
        findings.append(f"linha {line}: backfill sem INSERT INTO verificável")
    used_targets = {target.lower() for target in inserts}
    undeclared = used_targets - set(declared_targets)
    if undeclared:
        findings.append(
            f"linha {line}: target fora da allowlist: {', '.join(sorted(undeclared))}"
        )
    if "SELECT" not in upper:
        findings.append(f"linha {line}: backfill deve usar INSERT ... SELECT")
    if "NOT EXISTS" not in upper and not re.search(
        r"\bON\s+CONFLICT\b.*?\bDO\s+NOTHING\b",
        upper,
        flags=re.DOTALL,
    ):
        findings.append(
            f"linha {line}: backfill sem prova estática de idempotência"
        )
    return findings, used_targets


def _numero_da_revisao(path: Path) -> int | None:
    """Prefixo numérico do arquivo (``158_x.py`` → 158); None se não numerado."""
    match = re.match(r"(\d+)_", path.name)
    return int(match.group(1)) if match else None


def _tabelas_criadas_no_upgrade(upgrade: ast.FunctionDef) -> set[str]:
    """Tabelas que ``op.create_table("x", ...)`` cria no próprio ``upgrade()``:
    constraint sobre elas não varre linha nenhuma."""
    criadas: set[str] = set()
    for node in ast.walk(upgrade):
        if isinstance(node, ast.Call) and _op_call_name(node) == "create_table":
            nome = _extract_string_from_call(node)
            if nome:
                criadas.add(nome.lower())
    return criadas


def _constraint_com_validacao_findings(
    call: ast.Call,
    op_name: str,
    tabelas_novas: set[str],
    numero_revisao: int | None,
) -> str | None:
    """DB-08: FK/CHECK só é expand-only com ``NOT VALID`` ou em tabela nova."""
    if numero_revisao is not None and numero_revisao < NOT_VALID_OBRIGATORIO_A_PARTIR_DE:
        return None  # catraca: histórico já aplicado não é reescrito
    if _keyword_literal(call, "postgresql_not_valid") is True:
        return None
    # op.create_foreign_key(name, source_table, ...) / op.create_check_constraint(name, table, ...)
    tabela = None
    if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant) and isinstance(call.args[1].value, str):
        tabela = call.args[1].value.lower()
    else:
        tabela_kw = _keyword_literal(call, "source_table") or _keyword_literal(call, "table_name")
        if isinstance(tabela_kw, str):
            tabela = tabela_kw.lower()
    if tabela and tabela in tabelas_novas:
        return None
    line = getattr(call, "lineno", 0)
    return (
        f"linha {line}: op.{op_name} sem postgresql_not_valid=True valida a tabela "
        "inteira sob lock — exige revisão humana (ou NOT VALID + VALIDATE em migration separada)"
    )


def _classify(revision: Revision) -> tuple[list[str], str]:
    tree = ast.parse(
        revision.path.read_text(encoding="utf-8"),
        filename=str(revision.path),
    )
    upgrade = _upgrade_function(tree, revision.path)
    findings = _static_upgrade_shape_findings(upgrade)
    tabelas_novas = _tabelas_criadas_no_upgrade(upgrade)
    numero_revisao = _numero_da_revisao(revision.path)
    policy = _assignment(tree, "deployment_policy")
    policy_name = policy if isinstance(policy, str) else "expand_only"
    declared_targets = _declared_backfill_targets(tree)
    used_backfill_targets: set[str] = set()
    backfill_execute_count = 0

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
        "alter_column",  # tratado por handler próprio (widening estática)
        "rename_table",
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

        if op_name is None and attr_name in {"execute", "exec_driver_sql"}:
            findings.append(
                f"linha {line}: chamada .{attr_name} exige revisão humana"
            )
            continue
        if op_name is None:
            continue

        if op_name == "execute":
            if policy == ADDITIVE_DATA_BACKFILL:
                backfill_execute_count += 1
                sql_findings, targets = _safe_backfill_sql_findings(
                    node,
                    declared_targets,
                )
                findings.extend(sql_findings)
                used_backfill_targets.update(targets)
            else:
                sql = _extract_string_from_call(node)
                if sql and _is_safe_expand_ddl(sql):
                    continue
                findings.append(f"linha {line}: op.execute exige revisão")
        elif op_name == "add_column":
            ok, reason = _column_is_expand_only(node)
            if not ok:
                findings.append(f"linha {line}: {reason}")
        elif op_name == "create_index":
            if _keyword_literal(node, "unique") is True:
                findings.append(
                    f"linha {line}: índice UNIQUE exige revisão de dados/lock"
                )
        elif op_name in _CONSTRAINTS_COM_VALIDACAO:
            motivo = _constraint_com_validacao_findings(
                node, op_name, tabelas_novas, numero_revisao
            )
            if motivo:
                findings.append(motivo)
        elif op_name == "alter_column":
            # Expansão pura de tamanho (VARCHAR(n)→VARCHAR(m), n<m) é
            # expand-only por construção: PostgreSQL nunca recusa dados
            # existentes em widening. Qualquer outra alteração de coluna
            # segue exigindo revisão humana.
            widening, motivo = _alter_column_is_expand_only(node)
            if not widening:
                findings.append(f"linha {line}: {motivo}")
        elif op_name in review_required:
            # ``human_reviewed_drop``: política declarada que formaliza a
            # revisão humana exigida para operações destrutivas — a declaração
            # explícita no módulo É o registro de revisão (homologação
            # M02/M11, 16/08/2026). A catraca de forma estática permanece
            # ativa: corpos dinâmicos continuam reprovando.
            if policy != HUMAN_REVIEWED_DROP:
                findings.append(f"linha {line}: op.{op_name} exige revisão")
        elif op_name not in allowed:
            findings.append(f"linha {line}: op.{op_name} não está na allowlist")

    if policy is not None and policy not in {
        ADDITIVE_DATA_BACKFILL,
        HUMAN_REVIEWED_DROP,
    }:
        findings.append(f"deployment_policy desconhecida: {policy!r}")
    if policy == ADDITIVE_DATA_BACKFILL:
        if not backfill_execute_count:
            findings.append("backfill declarado sem op.execute")
        if declared_targets is None:
            findings.append("data_backfill_targets ausente ou inválido")
        elif used_backfill_targets != set(declared_targets):
            missing = set(declared_targets) - used_backfill_targets
            if missing:
                findings.append(
                    "targets declarados sem INSERT correspondente: "
                    + ", ".join(sorted(missing))
                )
    return findings, policy_name


def evaluate(directory: Path, current_revision: str) -> dict[str, object]:
    revisions = _load_revisions(directory)
    target, pending = _linear_pending_path(revisions, current_revision)
    migrations: list[dict[str, object]] = []
    for revision in pending:
        reasons, policy = _classify(revision)
        migrations.append(
            {
                "revision": revision.revision,
                "file": revision.path.name,
                "policy": policy,
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
