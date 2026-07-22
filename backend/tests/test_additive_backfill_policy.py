"""Regressões da política explícita de backfill aditivo no deploy."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_migration_compatibility.py"
SPEC = importlib.util.spec_from_file_location("migration_backfill_gate", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _base(directory: Path) -> None:
    (directory / "001.py").write_text(
        "from alembic import op\n"
        "import sqlalchemy as sa\n"
        "revision = '001'\n"
        "down_revision = None\n"
        "def upgrade():\n"
        "    op.create_table('base', sa.Column('id', sa.String()))\n"
        "def downgrade():\n"
        "    pass\n",
        encoding="utf-8",
    )


def _migration(
    directory: Path,
    sql_expression: str,
    *,
    policy: bool = True,
    targets: tuple[str, ...] = ("destino",),
) -> None:
    metadata = ""
    if policy:
        metadata = (
            "deployment_policy = 'additive_data_backfill'\n"
            f"data_backfill_targets = {targets!r}\n"
        )
    (directory / "002.py").write_text(
        "from alembic import op\n"
        "revision = '002'\n"
        "down_revision = '001'\n"
        + metadata
        + "def upgrade():\n"
        + f"    op.execute({sql_expression})\n"
        + "def downgrade():\n"
        + "    pass\n",
        encoding="utf-8",
    )


def _safe_sql() -> str:
    return repr(
        """
        INSERT INTO destino (id, nome)
        SELECT origem.id, origem.nome
        FROM origem
        WHERE NOT EXISTS (
            SELECT 1 FROM destino atual WHERE atual.id = origem.id
        )
        """
    )


def test_declared_literal_idempotent_insert_select_is_approved(tmp_path: Path):
    _base(tmp_path)
    _migration(tmp_path, _safe_sql())
    result = module.evaluate(tmp_path, "001")
    assert result["compatible"] is True
    assert result["migrations"][0]["policy"] == "additive_data_backfill"


def test_op_execute_without_explicit_policy_remains_blocked(tmp_path: Path):
    _base(tmp_path)
    _migration(tmp_path, _safe_sql(), policy=False)
    result = module.evaluate(tmp_path, "001")
    assert result["compatible"] is False
    assert any("op.execute exige revisão" in reason for reason in result["migrations"][0]["reasons"])


def test_update_is_forbidden_even_with_backfill_policy(tmp_path: Path):
    _base(tmp_path)
    sql = repr(
        """
        INSERT INTO destino (id) SELECT id FROM origem
        WHERE NOT EXISTS (SELECT 1 FROM destino WHERE destino.id = origem.id);
        UPDATE destino SET id = id;
        """
    )
    _migration(tmp_path, sql)
    result = module.evaluate(tmp_path, "001")
    assert result["compatible"] is False
    assert any("UPDATE" in reason for reason in result["migrations"][0]["reasons"])


def test_target_outside_declared_allowlist_is_blocked(tmp_path: Path):
    _base(tmp_path)
    _migration(tmp_path, _safe_sql(), targets=("outra_tabela",))
    result = module.evaluate(tmp_path, "001")
    assert result["compatible"] is False
    assert any("fora da allowlist" in reason for reason in result["migrations"][0]["reasons"])


def test_dynamic_sql_expression_is_blocked(tmp_path: Path):
    _base(tmp_path)
    _migration(tmp_path, "'INSERT INTO destino SELECT * FROM ' + 'origem'")
    result = module.evaluate(tmp_path, "001")
    assert result["compatible"] is False
    assert any("SQL de backfill não é string literal" in reason for reason in result["migrations"][0]["reasons"])


def test_insert_without_static_idempotency_is_blocked(tmp_path: Path):
    _base(tmp_path)
    _migration(tmp_path, repr("INSERT INTO destino (id) SELECT id FROM origem"))
    result = module.evaluate(tmp_path, "001")
    assert result["compatible"] is False
    assert any("sem prova estática de idempotência" in reason for reason in result["migrations"][0]["reasons"])
