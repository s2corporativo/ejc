"""Testes do classificador conservador de migrations de deploy."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_migration_compatibility.py"
SPEC = importlib.util.spec_from_file_location("migration_gate", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)
evaluate = module.evaluate


def _write(path: Path, revision: str, down: str | None, body: str) -> None:
    path.write_text(
        "from alembic import op\n"
        "import sqlalchemy as sa\n"
        f"revision = {revision!r}\n"
        f"down_revision = {down!r}\n"
        "def upgrade():\n"
        f"    {body}\n"
        "def downgrade():\n"
        "    pass\n",
        encoding="utf-8",
    )


def test_create_table_e_coluna_nullable_sao_expand_only(tmp_path: Path):
    _write(tmp_path / "001.py", "001", None, 'op.create_table("base", sa.Column("id", sa.String()))')
    _write(
        tmp_path / "002.py",
        "002",
        "001",
        'op.add_column("base", sa.Column("apelido", sa.String(), nullable=True))',
    )
    result = evaluate(tmp_path, "001")
    assert result["compatible"] is True
    assert result["pending_count"] == 1
    assert result["target_revision"] == "002"


def test_drop_e_execute_exigem_revisao(tmp_path: Path):
    _write(tmp_path / "001.py", "001", None, 'op.create_table("base", sa.Column("id", sa.String()))')
    _write(tmp_path / "002.py", "002", "001", 'op.drop_column("base", "legado")')
    result = evaluate(tmp_path, "001")
    assert result["compatible"] is False
    assert "drop_column" in result["migrations"][0]["reasons"][0]


def test_not_null_sem_default_nao_e_aprovado(tmp_path: Path):
    _write(tmp_path / "001.py", "001", None, 'op.create_table("base", sa.Column("id", sa.String()))')
    _write(
        tmp_path / "002.py",
        "002",
        "001",
        'op.add_column("base", sa.Column("codigo", sa.String(), nullable=False))',
    )
    result = evaluate(tmp_path, "001")
    assert result["compatible"] is False
    assert "NOT NULL" in result["migrations"][0]["reasons"][0]


def test_revision_atual_no_head_nao_tem_pendencia(tmp_path: Path):
    _write(tmp_path / "001.py", "001", None, 'op.create_table("base", sa.Column("id", sa.String()))')
    result = evaluate(tmp_path, "001")
    assert result["compatible"] is True
    assert result["pending_count"] == 0
