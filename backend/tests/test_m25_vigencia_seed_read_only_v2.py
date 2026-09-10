"""Regressão P0: M25 não promove vigência e não depende de path da VPS."""
from __future__ import annotations

import ast
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "inventory"
    / "m25_fix_vigencia_seeds.py"
)


def _source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _sql_auditoria() -> str:
    tree = ast.parse(_source())
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "_SQL_AUDITORIA" for t in node.targets):
            continue
        assert isinstance(node.value, ast.Call)
        assert node.value.args
        return ast.literal_eval(node.value.args[0])
    raise AssertionError("_SQL_AUDITORIA não encontrada")


def test_m25_sql_e_somente_leitura():
    sql = _sql_auditoria().strip().upper()

    assert sql.startswith("SELECT")
    assert "UPDATE KNOWLEDGE_DOCS" not in sql
    assert "INSERT INTO" not in sql
    assert "DELETE FROM" not in sql


def test_m25_nao_mantem_patch_de_promocao():
    tree = ast.parse(_source())
    nomes_atribuidos = {
        target.id
        for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        for target in (
            node.targets if isinstance(node, ast.Assign) else [node.target]
        )
        if isinstance(target, ast.Name)
    }

    assert "PATCH_JSON" not in nomes_atribuidos


def test_m25_nao_depende_de_path_absoluto_da_vps():
    source = _source()

    assert "/home/ubuntu/ejc_repo/backend" not in source
    assert 'if __name__ == "__main__"' in source
