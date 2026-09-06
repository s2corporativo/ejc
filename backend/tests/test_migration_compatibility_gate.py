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


def _base(tmp_path: Path) -> None:
    _write(
        tmp_path / "001.py",
        "001",
        None,
        'op.create_table("base", sa.Column("id", sa.String()))',
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
    _base(tmp_path)
    _write(
        tmp_path / "002.py",
        "002",
        "001",
        'op.add_column("base", sa.Column("novo", sa.String(), nullable=True))',
        'op.drop_column("base", "novo")',
    )
    assert evaluate(tmp_path, "001")["compatible"] is True


def test_drop_execute_e_exec_driver_sql_exigem_revisao(tmp_path: Path):
    _base(tmp_path)
    _write(tmp_path / "002.py", "002", "001", 'op.drop_column("base", "legado")')
    result = evaluate(tmp_path, "001")
    assert result["compatible"] is False
    assert any("drop_column" in reason for reason in result["migrations"][0]["reasons"])

    _write(
        tmp_path / "002.py",
        "002",
        "001",
        'op.get_bind().execute(sa.text("UPDATE base SET id=id"))',
    )
    result = evaluate(tmp_path, "001")
    assert result["compatible"] is False
    assert any("execute" in reason for reason in result["migrations"][0]["reasons"])

    _write(
        tmp_path / "002.py",
        "002",
        "001",
        'op.get_bind().exec_driver_sql("DROP TABLE base")',
    )
    result = evaluate(tmp_path, "001")
    assert result["compatible"] is False
    assert any(
        "exec_driver_sql" in reason
        for reason in result["migrations"][0]["reasons"]
    )


def test_helper_local_e_fluxo_dinamico_nao_contornam_gate(tmp_path: Path):
    _base(tmp_path)
    (tmp_path / "002.py").write_text(
        "from alembic import op\n"
        "revision = '002'\n"
        "down_revision = '001'\n"
        "def _oculto():\n"
        "    op.drop_table('base')\n"
        "def upgrade():\n"
        "    _oculto()\n"
        "def downgrade():\n"
        "    pass\n",
        encoding="utf-8",
    )
    result = evaluate(tmp_path, "001")
    assert result["compatible"] is False
    assert any("fora de op.*" in reason for reason in result["migrations"][0]["reasons"])

    _write(
        tmp_path / "002.py",
        "002",
        "001",
        'if True:\n        op.create_table("nova", sa.Column("id", sa.String()))',
    )
    result = evaluate(tmp_path, "001")
    assert result["compatible"] is False
    assert any("If" in reason for reason in result["migrations"][0]["reasons"])


def test_not_null_sem_default_e_indice_unique_nao_sao_aprovados(tmp_path: Path):
    _base(tmp_path)
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


def test_not_null_com_server_default_estatico_e_aprovado(tmp_path: Path):
    _base(tmp_path)
    _write(
        tmp_path / "002.py",
        "002",
        "001",
        'op.add_column("base", sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()))',
    )
    result = evaluate(tmp_path, "001")
    assert result["compatible"] is True


def test_revision_atual_no_head_nao_tem_pendencia(tmp_path: Path):
    _base(tmp_path)
    result = evaluate(tmp_path, "001")
    assert result["compatible"] is True
    assert result["pending_count"] == 0


def test_heads_multiplos_e_caminho_ramificado_falham(tmp_path: Path):
    _write(tmp_path / "001.py", "001", None, "pass")
    _write(tmp_path / "002a.py", "002a", "001", "pass")
    _write(tmp_path / "002b.py", "002b", "001", "pass")
    with pytest.raises(RuntimeError, match="head único"):
        evaluate(tmp_path, "001")


# ── DB-08 (auditoria de camadas 06/09/2026): FK/CHECK exigem NOT VALID ──────
# ``create_foreign_key``/``create_check_constraint`` em tabela existente validam
# a tabela inteira sob lock no ALTER TABLE — não é expand-only. Só passam com
# ``postgresql_not_valid=True`` (ou ``ALTER TABLE ... NOT VALID`` literal), ou
# quando a tabela nasce no mesmo ``upgrade()``. ``create_index`` continua
# expand-only. Arquivos ``NNN_nome.py`` abaixo de 158 ficam na catraca antiga.

def test_fk_e_check_sem_not_valid_exigem_revisao(tmp_path: Path):
    _base(tmp_path)
    _write(
        tmp_path / "002.py",
        "002",
        "001",
        'op.create_foreign_key("fk_base_x", "base", "outra", ["x"], ["id"])',
    )
    result = evaluate(tmp_path, "001")
    assert result["compatible"] is False
    assert any(
        "create_foreign_key" in r and "not_valid" in r
        for r in result["migrations"][0]["reasons"]
    )

    _write(
        tmp_path / "002.py",
        "002",
        "001",
        'op.create_check_constraint("ck_base_status", "base", "status IN (\'a\')")',
    )
    result = evaluate(tmp_path, "001")
    assert result["compatible"] is False
    assert any("create_check_constraint" in r for r in result["migrations"][0]["reasons"])


def test_fk_e_check_com_postgresql_not_valid_sao_expand_only(tmp_path: Path):
    _base(tmp_path)
    _write(
        tmp_path / "002.py",
        "002",
        "001",
        'op.create_foreign_key("fk_base_x", "base", "outra", ["x"], ["id"], postgresql_not_valid=True)',
    )
    assert evaluate(tmp_path, "001")["compatible"] is True

    _write(
        tmp_path / "002.py",
        "002",
        "001",
        'op.create_check_constraint("ck_base_status", "base", "status IN (\'a\')", postgresql_not_valid=True)',
    )
    assert evaluate(tmp_path, "001")["compatible"] is True


def test_alter_table_add_constraint_not_valid_literal_e_expand_only(tmp_path: Path):
    _base(tmp_path)
    _write(
        tmp_path / "002.py",
        "002",
        "001",
        'op.execute("ALTER TABLE base ADD CONSTRAINT ck_base_status '
        'CHECK (status IN (\'a\', \'b\')) NOT VALID")',
    )
    assert evaluate(tmp_path, "001")["compatible"] is True

    # Sem NOT VALID o mesmo ALTER continua exigindo revisão.
    _write(
        tmp_path / "002.py",
        "002",
        "001",
        'op.execute("ALTER TABLE base ADD CONSTRAINT ck_base_status CHECK (status IN (\'a\'))")',
    )
    assert evaluate(tmp_path, "001")["compatible"] is False


def test_constraint_em_tabela_criada_no_mesmo_upgrade_e_expand_only(tmp_path: Path):
    _base(tmp_path)
    _write(
        tmp_path / "002.py",
        "002",
        "001",
        'op.create_table("nova", sa.Column("id", sa.String()), sa.Column("base_id", sa.String()))\n'
        '    op.create_foreign_key("fk_nova_base", "nova", "base", ["base_id"], ["id"])\n'
        '    op.create_check_constraint("ck_nova_id", "nova", "id <> \'\'")',
    )
    assert evaluate(tmp_path, "001")["compatible"] is True


def test_create_index_continua_expand_only_e_catraca_poupa_historico(tmp_path: Path):
    _base(tmp_path)
    _write(
        tmp_path / "002.py",
        "002",
        "001",
        'op.create_index("ix_base_x", "base", ["x"])',
    )
    assert evaluate(tmp_path, "001")["compatible"] is True

    # Arquivo numerado ABAIXO da catraca (153_*): FK sem NOT VALID passa, como
    # já passou na main. Numerado a partir de 158: reprova.
    _write(
        tmp_path / "153_legado.py",
        "153",
        "001",
        'op.create_foreign_key("fk_base_x", "base", "outra", ["x"], ["id"])',
    )
    (tmp_path / "002.py").unlink()
    assert evaluate(tmp_path, "001")["compatible"] is True
    (tmp_path / "153_legado.py").unlink()
    _write(
        tmp_path / "158_novo.py",
        "158",
        "001",
        'op.create_foreign_key("fk_base_x", "base", "outra", ["x"], ["id"])',
    )
    assert evaluate(tmp_path, "001")["compatible"] is False
