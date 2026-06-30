"""Isolamento do RAG por cliente — Fase 3B.

Garante que o filtro fail-closed está presente e é aplicado nas consultas
(protege contra regressão do vazamento cruzado entre clientes).
"""
import inspect

import pytest

from app.services.ai_service import (
    _RESTRICTED_CATS,
    _FILTRO_ESCOPO_RAG,
    buscar_contexto_rag,
)


def test_categorias_restritas():
    for c in ("peca_interna", "peca_escritorio", "precedente_interno"):
        assert c in _RESTRICTED_CATS


def test_fragmento_de_filtro():
    assert "kd.client_id = :scope_cli" in _FILTRO_ESCOPO_RAG
    assert "kd.categoria <> ALL(:restr_cats)" in _FILTRO_ESCOPO_RAG


def test_assinatura_tem_escopo():
    assert "scope_client_id" in inspect.signature(buscar_contexto_rag).parameters


def test_limiar_de_similaridade_rag04():
    # RAG-04: a busca semântica tem um teto de distância (= 1 - similaridade mínima).
    from app.services.ai_service import _RAG_MAX_DIST, _RAG_MIN_SIM
    assert 0.0 < _RAG_MAX_DIST < 1.0
    assert _RAG_MAX_DIST == pytest.approx(1.0 - _RAG_MIN_SIM, abs=1e-9)


class _CaptureDB:
    """Captura o SQL/params da última consulta; retorna zero linhas."""
    def __init__(self):
        self.sql = ""
        self.params = {}

    async def execute(self, sql, params=None):
        self.sql = str(sql)
        self.params = params or {}
        return []


async def test_consulta_aplica_escopo():
    db = _CaptureDB()
    # Sem embeddings (default) cai na busca textual — que deve conter o filtro.
    await buscar_contexto_rag(db, "consulta de teste sobre tese qualquer", limite=3)
    assert "client_id = :scope_cli" in db.sql
    assert "scope_cli" in db.params
    assert "restr_cats" in db.params
    # Fail-closed: sem escopo, scope_cli é string vazia (nunca casa um UUID).
    assert db.params["scope_cli"] == ""
