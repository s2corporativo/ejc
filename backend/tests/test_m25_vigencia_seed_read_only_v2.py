"""Regressão P0: M25 é read-only, público e rastreável."""
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


def test_m25_restringe_a_base_publica_global():
    sql = _sql_auditoria().upper()

    assert "CLIENT_ID IS NULL" in sql
    assert "CASE_ID IS NULL" in sql
    assert "BASE_RAG = 'PUBLICA'" in sql


def test_m25_identifica_versao_e_vigencia_do_registro():
    sql = _sql_auditoria().upper()

    assert "VERSAO" in sql
    assert "VIGENTE" in sql
    assert "ORDER BY CHAVE_ORIGEM, VERSAO DESC" in sql


def test_m25_marcador_inferencia_espelha_gate_rag():
    sql = _sql_auditoria().upper()

    assert "NULLIF(BTRIM" in sql
    assert "LEGAL_STATUS_INFERIDO_EM" in sql
    assert "IS NOT NULL" in sql


def test_m25_nao_expoe_id_de_curador_na_saida():
    source = _source()
    sql = _sql_auditoria()

    assert "legal_status_origem_categoria" in source
    assert "THEN 'curadoria'" in sql
    assert 'row["legal_status_origem"]' not in source


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
