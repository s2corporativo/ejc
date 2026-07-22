"""Testes do classificador conservador de migrations de deploy."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_migration_compatibility.py"
SPEC = importlib.util.spec_from_file_location("migration_gate", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)
evaluate = module.evaluate


def _write(
    path: Path,
    revision: str,
    down: str | None,
    upgrade_body: str,
    downgrade_body: str = "pass",
) -> None:
    path.write_text(
        "from alembic import op\n"
        "import sqlalchemy as sa\n"
        f"revision = {revision!r}\n"
        f"down_revision = {down!r}\n"
        "def upgrade():\n"
        f"    {upgrade_body}\n"
        "def downgrade():\n"
        f"    {downgrade_body}\n",
        encoding="utf-8",
    )


def test_create_table_e_coluna_nullable_sao_expand_only(tmp_path: Path):
    _write(
        tmp_path / "001.py",
        "001",
        None,
        'op.create_table("base", sa.Column("id", sa.String()))',
        'op.drop_table("base")',
    )
    _write(
        tmp_path / "002.py",
        "002",
        "001",
        'op.add_column("base", sa.Column("apelido", sa.String(), nullable=True))',
        'op.drop_column("base", "apelido")',
    )
    result = evaluate(tmp_path, "001")
    assert result["compatible"] is True
    assert result["pending_count"] == 1
    assert result["target_revision"] == "002"


def test_downgrade_destrutivo_nao_contamina_classificacao_do_upgrade(tmp_path: Path):
    _write(
        tmp_path / "001.py",
        "001",
        None,
        'op.create_table("base", sa.Column("id", sa.String()))',
    )
    _write(
        tmp_path / "002.py",
        "002",
        "001",
        'op.add_column("base", sa.Column("novo", sa.String(), nullable=True))',
        'op.drop_column("base", "novo")',
    )
    assert evaluate(tmp_path, "001")["compatible"] is True


def test_drop_execute_e_bind_execute_exigem_revisao(tmp_path: Path):
    _write(
        tmp_path / "001.py",
        "001",
        None,
        'op.create_table("base", sa.Column("id", sa.String()))',
    )
    _write(tmp_path / "002.py", "002", "001", 'op.drop_column("base", "legado")')
    result = evaluate(tmp_path, "001")
    assert result["compatible"] is False
    assert "drop_column" in result["migrations"][0]["reasons"][0]

    _write(
        tmp_path / "002.py",
        "002",
        "001",
        'op.get_bind().execute(sa.text("UPDATE base SET id=id"))',
    )
    result = evaluate(tmp_path, "001")
    assert result["compatible"] is False
    assert any("execute" in reason for reason in result["migrations"][0]["reasons"])


def test_not_null_sem_default_e_indice_unique_nao_sao_aprovados(tmp_path: Path):
    _write(
        tmp_path / "001.py",
        "001",
        None,
        'op.create_table("base", sa.Column("id", sa.String()))',
    )
    _write(
        tmp_path / "002.py",
        "002",
        "001",
        'op.add_column("base", sa.Column("codigo", sa.String(), nullable=False))',
    )
    result = evaluate(tmp_path, "001")
    assert result["compatible"] is False
    assert any("NOT NULL" in reason for reason in result["migrations"][0]["reasons"])

    _write(
        tmp_path / "002.py",
        "002",
        "001",
        'op.create_index("uq_base", "base", ["id"], unique=True)',
    )
    result = evaluate(tmp_path, "001")
    assert result["compatible"] is False
    assert any("UNIQUE" in reason for reason in result["migrations"][0]["reasons"])


def test_not_null_com_server_default_e_aprovado(tmp_path: Path):
    _write(
        tmp_path / "001.py",
        "001",
        None,
        'op.create_table("base", sa.Column("id", sa.String()))',
    )
    _write(
        tmp_path / "002.py",
        "002",
        "001",
        'op.add_column("base", sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()))',
    )
    result = evaluate(tmp_path, "001")
    assert result["compatible"] is True


def test_revision_atual_no_head_nao_tem_pendencia(tmp_path: Path):
    _write(
        tmp_path / "001.py",
        "001",
        None,
        'op.create_table("base", sa.Column("id", sa.String()))',
    )
    result = evaluate(tmp_path, "001")
    assert result["compatible"] is True
    assert result["pending_count"] == 0


def test_heads_multiplos_e_caminho_ramificado_falham(tmp_path: Path):
    _write(tmp_path / "001.py", "001", None, "pass")
    _write(tmp_path / "002a.py", "002a", "001", "pass")
    _write(tmp_path / "002b.py", "002b", "001", "pass")
    with pytest.raises(RuntimeError, match="head único"):
        evaluate(tmp_path, "001")
