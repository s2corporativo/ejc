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
    # A-2 (2026-07-17): o limiar virou CONFIGURÁVEL (RAG_MIN_SIM) via _rag_max_dist().
    from app.services.ai_service import _rag_max_dist, _RAG_MIN_SIM_DEFAULT
    from app.core.config import get_settings
    d = _rag_max_dist()
    assert 0.0 < d < 1.0
    sim = float(get_settings().RAG_MIN_SIM)
    assert d == pytest.approx(1.0 - sim, abs=1e-9)
    assert _RAG_MIN_SIM_DEFAULT == pytest.approx(0.55, abs=1e-9)  # default de fábrica


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


# ── Bloco 5 — isolamento por cliente aplicado nas chamadas ────────────────────

class _ResultCaso:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _DBCaso:
    """Fake DB que devolve o client_id de um caso (ou None se inexistente)."""
    def __init__(self, client_id):
        self._cid = client_id

    async def execute(self, sql, params=None):
        return _ResultCaso((self._cid,) if self._cid is not None else None)


async def test_escopo_sem_caso_e_fail_closed():
    """Sem case_id, o escopo é None → RAG mantém fail-closed (nada restrito)."""
    from app.services.ai_service import _escopo_cliente_do_caso
    assert await _escopo_cliente_do_caso(_DBCaso("qualquer"), None) is None


async def test_escopo_deriva_client_id_do_caso():
    """Com case_id, o escopo é EXATAMENTE o client_id daquele caso."""
    from app.services.ai_service import _escopo_cliente_do_caso
    assert await _escopo_cliente_do_caso(_DBCaso("cliente-A"), "caso-1") == "cliente-A"


async def test_escopo_caso_inexistente_e_fail_closed():
    """Caso inexistente/deletado → None (não vaza para escopo vazio de outro)."""
    from app.services.ai_service import _escopo_cliente_do_caso
    assert await _escopo_cliente_do_caso(_DBCaso(None), "caso-fantasma") is None


async def test_escopo_nao_vazio_propaga_ao_param_sql():
    """Prova a ponta final do elo: um escopo de cliente chega ao scope_cli do SQL
    (com o filtro já validado, isolamento = filtro correto + client_id correto)."""
    db = _CaptureDB()
    await buscar_contexto_rag(db, "consulta", limite=3, scope_client_id="cliente-A")
    assert db.params["scope_cli"] == "cliente-A"
