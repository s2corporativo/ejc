"""P0.1 — vigência jurídica integrada ao RAG e citation gate (Issue #826).

Testes unitários/fakes: sem rede, sem dados reais e sem depender do banco de
produção. A prova row-level fica a cargo do job DB do CI.
"""
from __future__ import annotations

import pytest

from app.services import ai_service
from app.services.ai_service import (
    _FILTRO_VIGENCIA_ATUAL_RAG,
    _filtros_gate_rag,
    buscar_contexto_rag,
)
from app.services.citation_gate import avaliar_bloqueantes


@pytest.fixture(autouse=True)
def _sem_embeddings(monkeypatch):
    from app.services import embedding_service

    monkeypatch.setattr(embedding_service, "disponivel", lambda: False)


class _CaptureDB:
    def __init__(self):
        self.sql = ""
        self.params = {}

    async def execute(self, sql, params=None):
        self.sql = str(sql)
        self.params = params or {}
        return []


def test_gate_atual_exige_status_vigente_em_legislacao():
    gate = _filtros_gate_rag(False, incluir_historico=False)
    assert _FILTRO_VIGENCIA_ATUAL_RAG in gate
    for chave in ("legal_status", "situacao_normativa", "vigencia_status"):
        assert f"kd.extra->>'{chave}'" in _FILTRO_VIGENCIA_ATUAL_RAG
    assert "LIKE '%legisl%'" in _FILTRO_VIGENCIA_ATUAL_RAG
    assert "<> 'vigente'" in _FILTRO_VIGENCIA_ATUAL_RAG


def test_gate_historico_preserva_controles_e_libera_so_vigencia_juridica():
    atual = _filtros_gate_rag(False, incluir_historico=False)
    historico = _filtros_gate_rag(False, incluir_historico=True)

    assert _FILTRO_VIGENCIA_ATUAL_RAG in atual
    assert _FILTRO_VIGENCIA_ATUAL_RAG not in historico
    # Os controles anteriores continuam em ambos os modos.
    for fragmento in (
        ai_service._FILTRO_GATE_RAG,
        ai_service._FILTRO_APROVADO_RAG,
        ai_service._FILTRO_SUMULAS_QUARENTENA,
        ai_service._FILTRO_FICTICIO_RAG,
    ):
        assert fragmento in atual
        assert fragmento in historico


async def test_busca_textual_propaga_modo_de_vigencia_ao_sql():
    atual = _CaptureDB()
    await buscar_contexto_rag(atual, "artigo tutela urgencia", limite=3)
    assert _FILTRO_VIGENCIA_ATUAL_RAG in atual.sql

    historico = _CaptureDB()
    await buscar_contexto_rag(
        historico,
        "artigo tutela urgencia",
        limite=3,
        incluir_historico=True,
    )
    assert _FILTRO_VIGENCIA_ATUAL_RAG not in historico.sql


def test_artigo_nao_confirmado_com_aviso_real_bloqueia_sem_modo_estrito():
    rel = {
        "citacoes": [{
            "status": "identificada",
            "tipo": "artigo",
            "citacao": "art. 300 CPC",
            "aviso": (
                "Artigo não localizado na legislação ingerida na base interna — "
                "confira o texto legal vigente antes de citar."
            ),
        }]
    }
    bloqueantes = avaliar_bloqueantes(rel, modo_estrito=False)
    assert len(bloqueantes) == 1
    assert bloqueantes[0]["tipo"] == "artigo"
    assert "vigência" in bloqueantes[0]["motivo"]


def test_artigo_em_versao_nao_atual_bloqueia_sem_modo_estrito():
    rel = {
        "citacoes": [{
            "status": "possivelmente_desatualizada",
            "tipo": "artigo",
            "citacao": "art. 300 CPC",
            "aviso": "Localizado apenas em versão superada.",
        }]
    }
    bloqueantes = avaliar_bloqueantes(rel, modo_estrito=False)
    assert len(bloqueantes) == 1
    assert "não apta" in bloqueantes[0]["motivo"]


def test_sumula_identificada_continua_dependendo_do_modo_estrito():
    rel = {
        "citacoes": [{
            "status": "identificada",
            "tipo": "sumula",
            "citacao": "Súmula 7 STJ",
            "aviso": "Referência plausível, mas não confirmada.",
        }]
    }
    assert avaliar_bloqueantes(rel, modo_estrito=False) == []
    assert avaliar_bloqueantes(rel, modo_estrito=True)
