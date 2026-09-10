"""Regressão P0: utilitário histórico M25 nunca promove vigência por fonte oficial."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def _carregar_modulo():
    raiz = Path(__file__).resolve().parents[2]
    path = raiz / "scripts" / "inventory" / "m25_fix_vigencia_seeds.py"
    spec = importlib.util.spec_from_file_location("m25_vigencia_seed_read_only", path)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_m25_vigencia_seed_e_somente_leitura():
    modulo = _carregar_modulo()
    sql = str(modulo._SQL_AUDITORIA).strip().upper()

    assert sql.startswith("SELECT")
    assert "UPDATE KNOWLEDGE_DOCS" not in sql
    assert "INSERT INTO" not in sql
    assert "DELETE FROM" not in sql


def test_m25_nao_mantem_patch_de_promocao_automatica():
    modulo = _carregar_modulo()

    assert not hasattr(modulo, "PATCH_JSON")
    assert modulo.SLUGS == ("planalto:cpc", "planalto:cf88")
