"""Limites Pydantic dos schemas de novos_modulos (Bloco 3, Fix 2).

Testes puros — não tocam banco. Valores monetários/percentuais fora do
intervalo e strings livres acima do tamanho devem gerar ValidationError (→ 422
na rota), sem enfraquecer os nomes de campo existentes.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.routers.novos_modulos import PrecificacaoCreate, AmbientalCreate


# ── PrecificacaoCreate ──────────────────────────────────────────────────────────

def test_precificacao_valida():
    obj = PrecificacaoCreate(
        area="civel", case_type="acao_ordinaria",
        base_amount=1000, percentage_of_value=20, exit_percentage=10,
        min_amount=500, max_amount=5000, notes="ok",
    )
    assert obj.base_amount == 1000
    assert obj.percentage_of_value == 20


def test_precificacao_base_amount_negativo():
    with pytest.raises(ValidationError):
        PrecificacaoCreate(area="civel", case_type="x", base_amount=-1)


def test_precificacao_percentual_acima_de_100():
    with pytest.raises(ValidationError):
        PrecificacaoCreate(area="civel", case_type="x", percentage_of_value=150)


def test_precificacao_exit_percentage_negativo():
    with pytest.raises(ValidationError):
        PrecificacaoCreate(area="civel", case_type="x", exit_percentage=-5)


def test_precificacao_notes_muito_longo():
    with pytest.raises(ValidationError):
        PrecificacaoCreate(area="civel", case_type="x", notes="a" * 3000)


# ── AmbientalCreate ─────────────────────────────────────────────────────────────

def test_ambiental_valido():
    obj = AmbientalCreate(
        numero_auto="AUTO-1", valor_multa=2500,
        reserva_legal_ha=12.5, observacoes="obs",
    )
    assert obj.valor_multa == 2500


def test_ambiental_valor_multa_negativo():
    with pytest.raises(ValidationError):
        AmbientalCreate(valor_multa=-10)


def test_ambiental_reserva_legal_negativa():
    with pytest.raises(ValidationError):
        AmbientalCreate(reserva_legal_ha=-1)


def test_ambiental_observacoes_muito_longo():
    with pytest.raises(ValidationError):
        AmbientalCreate(observacoes="a" * 3000)
