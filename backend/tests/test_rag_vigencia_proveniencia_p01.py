"""Contratos P0.1 do gate estrito de vigência normativa.

Uma string `legal_status='vigente'` não basta para fundamentação atual: o estado
precisa ter proveniência e carimbo de verificação positivos. Situações suspensa
ou parcialmente revogada permanecem úteis para pesquisa, mas não podem passar
como autoridade atual quando o modo estrito estiver ligado.
"""
from __future__ import annotations

import pytest

from app.services import ai_service
from app.services.ai_service import (
    _FILTRO_REVOGADA_RAG,
    _FILTRO_VIGENCIA_VERIFICADA_RAG,
    _filtros_gate_rag,
)


def _flag(monkeypatch, valor: bool) -> None:
    monkeypatch.setattr(
        ai_service.settings,
        "RAG_EXIGIR_VIGENCIA_VERIFICADA",
        valor,
    )


def test_gate_estrito_exige_status_vigente_com_proveniencia_positiva():
    filtro = _FILTRO_VIGENCIA_VERIFICADA_RAG

    assert "legal_status" in filtro
    assert "legal_status_origem" in filtro
    assert "legal_status_verificado_em" in filtro
    assert "legal_status_inferido_em" in filtro
    assert "'vigente'" in filtro


def test_status_inferido_nao_e_equivalente_a_verificado():
    filtro = _FILTRO_VIGENCIA_VERIFICADA_RAG

    # O SQL deve exigir ausência do carimbo de inferência na condição positiva,
    # em vez de aceitar qualquer string 'vigente' gravada automaticamente.
    assert "legal_status_inferido_em" in filtro
    assert "legal_status_verificado_em" in filtro


def test_suspensa_e_parcialmente_revogada_nao_passam_como_vigencia_atual():
    filtro = _FILTRO_VIGENCIA_VERIFICADA_RAG

    # Em modo estrito, a condição positiva é deliberadamente limitada a
    # `vigente`; estes estados podem existir no acervo, mas não fundamentar como
    # direito atual sem análise específica do alcance da suspensão/revogação.
    assert "'suspensa'" not in filtro.split("'vigente'", 1)[1]
    assert "'parcialmente_revogada'" not in filtro.split("'vigente'", 1)[1]


@pytest.mark.parametrize("estrito", [True, False])
def test_revogada_continua_bloqueada_independentemente_do_modo(monkeypatch, estrito):
    _flag(monkeypatch, estrito)
    assert _FILTRO_REVOGADA_RAG in _filtros_gate_rag(False)


def test_flag_false_nao_finge_que_houve_verificacao(monkeypatch):
    _flag(monkeypatch, False)
    gate = _filtros_gate_rag(False)

    assert _FILTRO_VIGENCIA_VERIFICADA_RAG not in gate
    assert _FILTRO_REVOGADA_RAG in gate
