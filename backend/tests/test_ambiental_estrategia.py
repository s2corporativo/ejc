"""Vertical Ambiental — Simulador de Estratégia do Auto de Infração.

Cobertura:
  • pagar_a_vista: desconto de 30% exato;
  • converter_servicos: teto 60% antes / 35% após a defesa, desembolso em dinheiro;
  • defender: valor esperado + faixa de sensibilidade ±15 p.p.;
  • prescricao: quinquenal transcorrida → aplicável, desembolso 0, recomendação;
  • recomendação determinística: menor desembolso entre aplicáveis;
  • consolidação valida contra o schema de resposta (ConsolidacaoOut);
  • guarda: payload gigante no /peca-conversao rejeitado pelo max_length.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.services.ambiental.estrategia_auto import simular_estrategia

HOJE = date(2026, 7, 5)
CIENCIA = date(2026, 6, 20)


def _cenario(res: dict, cid: str) -> dict:
    return next(c for c in res["cenarios"] if c["id"] == cid)


# ── Cenário 1: pagamento à vista ──────────────────────────────────────────────
def test_pagar_a_vista_desconto_30_exato():
    res = simular_estrategia(Decimal("10000"), CIENCIA, "antes_defesa",
                             Decimal("50"), None, None, hoje=HOJE)
    c = _cenario(res, "pagar_a_vista")
    assert c["aplicavel"] is True
    assert c["desembolso_estimado"] == Decimal("7000.00")
    assert c["memoria_calculo"] and c["base_legal"]


# ── Cenário 2: conversão em serviços ──────────────────────────────────────────
def test_converter_antes_defesa_60():
    res = simular_estrategia(Decimal("10000"), CIENCIA, "antes_defesa",
                             Decimal("50"), None, None, hoje=HOJE)
    c = _cenario(res, "converter_servicos")
    # convertida 60% = 6.000; desembolso em dinheiro = 10.000 − 6.000 = 4.000
    assert c["desembolso_estimado"] == Decimal("4000.00")


def test_converter_apos_defesa_35():
    res = simular_estrategia(Decimal("10000"), CIENCIA, "apos_defesa",
                             Decimal("50"), None, None, hoje=HOJE)
    c = _cenario(res, "converter_servicos")
    # convertida 35% = 3.500; desembolso em dinheiro = 6.500
    assert c["desembolso_estimado"] == Decimal("6500.00")


def test_converter_custo_recuperacao_nao_subtrai():
    res = simular_estrategia(Decimal("10000"), CIENCIA, "antes_defesa",
                             Decimal("50"), Decimal("2000"), None, hoje=HOJE)
    c = _cenario(res, "converter_servicos")
    # o custo de recuperação NÃO abate o desembolso — só aparece na memória
    assert c["desembolso_estimado"] == Decimal("4000.00")
    assert any("2.000" in m or "INVESTIMENTO" in m for m in c["memoria_calculo"])


# ── Cenário 3: defender ───────────────────────────────────────────────────────
def test_defender_valor_esperado_e_faixa():
    res = simular_estrategia(Decimal("10000"), CIENCIA, "antes_defesa",
                             Decimal("40"), None, None, hoje=HOJE)
    c = _cenario(res, "defender")
    # esperado 40% de 10.000 = 4.000
    assert c["desembolso_estimado"] == Decimal("4000.00")
    # faixa ±15 p.p.: 25% → 2.500 ; 55% → 5.500
    faixa = c["faixa_sensibilidade"]
    assert faixa["piso"] == Decimal("2500.00")
    assert faixa["teto"] == Decimal("5500.00")


def test_defender_faixa_clamp_0_100():
    res = simular_estrategia(Decimal("10000"), CIENCIA, "antes_defesa",
                             Decimal("90"), None, None, hoje=HOJE)
    faixa = _cenario(res, "defender")["faixa_sensibilidade"]
    # 90 + 15 = 105 → clamp 100 → teto = 10.000
    assert faixa["prob_alta_pct"] == Decimal("100")
    assert faixa["teto"] == Decimal("10000.00")


# ── Cenário 4: prescrição ─────────────────────────────────────────────────────
def test_prescricao_6_anos_aplicavel_e_recomendada():
    infracao = date(2020, 7, 5)  # 6 anos antes de HOJE
    res = simular_estrategia(Decimal("10000"), CIENCIA, "antes_defesa",
                             Decimal("50"), None, infracao, hoje=HOJE)
    c = _cenario(res, "prescricao")
    assert c["aplicavel"] is True
    assert c["desembolso_estimado"] == Decimal("0.00")
    assert res["recomendacao"]["cenario_id"] == "prescricao"


def test_prescricao_sem_data_infracao_inaplicavel():
    res = simular_estrategia(Decimal("10000"), CIENCIA, "antes_defesa",
                             Decimal("50"), None, None, hoje=HOJE)
    c = _cenario(res, "prescricao")
    assert c["aplicavel"] is False
    assert c["desembolso_estimado"] is None
    assert any("DATA DO FATO" in o or "data da infração" in o
               for o in c["observacoes"])


def test_prescricao_dentro_do_prazo_inaplicavel():
    infracao = date(2024, 1, 1)  # ~2,5 anos → dentro do quinquênio
    res = simular_estrategia(Decimal("10000"), CIENCIA, "antes_defesa",
                             Decimal("50"), None, infracao, hoje=HOJE)
    assert _cenario(res, "prescricao")["aplicavel"] is False


# ── Recomendação determinística ───────────────────────────────────────────────
def test_recomendacao_escolhe_menor_desembolso():
    # prob 20% → defender esperado 2.000 (< converter 4.000 < pagar 7.000).
    res = simular_estrategia(Decimal("10000"), CIENCIA, "antes_defesa",
                             Decimal("20"), None, None, hoje=HOJE)
    assert res["recomendacao"]["cenario_id"] == "defender"
    assert "2.000" in res["recomendacao"]["racional"]


def test_recomendacao_empate_ordem_pagar_converter_defender():
    # prob 40% → defender esperado 4.000 == converter 4.000 → converter vence
    # pelo desempate de ordem (pagar < converter < defender).
    res = simular_estrategia(Decimal("10000"), CIENCIA, "antes_defesa",
                             Decimal("40"), None, None, hoje=HOJE)
    assert res["recomendacao"]["cenario_id"] == "converter_servicos"


# ── Schema de resposta ────────────────────────────────────────────────────────
def test_consolidacao_valida_contra_schema_de_resposta():
    from app.routers.ambiental_estrategia import ConsolidacaoOut

    res = simular_estrategia(Decimal("10000"), CIENCIA, "antes_defesa",
                             Decimal("40"), Decimal("2000"), date(2020, 1, 1),
                             hoje=HOJE)
    out = ConsolidacaoOut.model_validate(res)
    assert len(out.cenarios) == 4
    assert out.recomendacao.cenario_id
    assert out.aviso_hitl and out.base_legal_geral
    # todos os cenários carregam base_legal (padrão Bancário: nunca número sem origem)
    assert all(c.base_legal for c in out.cenarios)
    defender = next(c for c in out.cenarios if c.id == "defender")
    assert defender.faixa_sensibilidade is not None


# ── Guarda de recurso no /peca-conversao ──────────────────────────────────────
def test_peca_conversao_rejeita_payload_gigante():
    from pydantic import ValidationError

    from app.routers.ambiental_estrategia import PecaConversaoIn

    res = simular_estrategia(Decimal("10000"), CIENCIA, "antes_defesa",
                             Decimal("40"), None, None, hoje=HOJE)
    base = {
        "consolidacao": res,
        "orgao_autuador": "IBAMA",
        "numero_auto": "123/2026",
    }
    # numero_auto acima do teto (max_length=128) → rejeitado antes do WeasyPrint
    with pytest.raises(ValidationError):
        PecaConversaoIn.model_validate(dict(base, numero_auto="X" * 500))
    # orgao_autuador acima do teto (max_length=2000)
    with pytest.raises(ValidationError):
        PecaConversaoIn.model_validate(dict(base, orgao_autuador="Y" * 5000))
