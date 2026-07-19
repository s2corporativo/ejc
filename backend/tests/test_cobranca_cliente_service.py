"""Régua de cobrança ao CLIENTE (cobranca_cliente_service): todas as faixas de
`degrau_aplicavel` (função pura), não-repetição de degrau, escalada ao
advogado e template determinístico cordial. Sem banco nem rede."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services.cobranca_cliente_service import (
    ASSINATURA_AUTOMATICA,
    degrau_aplicavel,
    montar_email_cobranca,
)

HOJE = date(2026, 7, 11)


def _venc(dias_atraso: int) -> date:
    """Vencimento tal que (hoje - vencimento) == dias_atraso."""
    return HOJE - timedelta(days=dias_atraso)


# ── Faixas ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("dias_para_vencer", [1, 2, 3])
def test_d_menos_3_para_parcela_a_vencer(dias_para_vencer):
    assert degrau_aplicavel(HOJE, HOJE + timedelta(days=dias_para_vencer),
                            set()) == "d-3"


def test_sem_degrau_fora_da_janela_a_vencer():
    # Vence em 4+ dias ou vence HOJE (dias==0): nenhum degrau.
    assert degrau_aplicavel(HOJE, HOJE + timedelta(days=4), set()) is None
    assert degrau_aplicavel(HOJE, HOJE, set()) is None


@pytest.mark.parametrize("dias", [1, 3, 6])
def test_d_mais_1_para_atraso_de_1_a_6_dias(dias):
    assert degrau_aplicavel(HOJE, _venc(dias), set()) == "d+1"


@pytest.mark.parametrize("dias", [7, 10, 14])
def test_d_mais_7_para_atraso_de_7_a_14_dias(dias):
    assert degrau_aplicavel(HOJE, _venc(dias), set()) == "d+7"


@pytest.mark.parametrize("dias", [15, 16, 40])
def test_d_mais_15_para_atraso_de_15_ou_mais(dias):
    assert degrau_aplicavel(HOJE, _venc(dias), set()) == "d+15"


# ── Escalada e não-repetição ───────────────────────────────────────────────────

def test_escalada_exige_16_dias_e_d15_ja_enviado():
    assert degrau_aplicavel(HOJE, _venc(16), {"d+15"}) == "escalado_advogado"
    # Com 15 dias exatos (d+15 recém-enviado), ainda não escala.
    assert degrau_aplicavel(HOJE, _venc(15), {"d+15"}) is None
    # Sem d+15 enviado, 16+ dias manda d+15 primeiro (mais avançado da janela).
    assert degrau_aplicavel(HOJE, _venc(20), set()) == "d+15"


def test_escalada_nao_repete():
    assert degrau_aplicavel(
        HOJE, _venc(30), {"d+15", "escalado_advogado"}
    ) is None


@pytest.mark.parametrize("dias,degrau", [
    # 15 dias exatos: d+15 enviado e ainda sem gatilho de escalada (>=16).
    (-2, "d-3"), (3, "d+1"), (10, "d+7"), (15, "d+15"),
])
def test_degrau_ja_enviado_nunca_repete(dias, degrau):
    assert degrau_aplicavel(HOJE, _venc(dias), {degrau}) is None


def test_maximo_um_degrau_por_execucao_e_degraus_pulados_nao_voltam():
    # Parcela entra na régua já com 10 dias de atraso: d+1 é "pulado" —
    # aplica-se apenas o mais avançado da janela atual (d+7).
    assert degrau_aplicavel(HOJE, _venc(10), set()) == "d+7"
    # No dia seguinte (mesma janela), d+7 já enviado → nada (não regride a d+1).
    assert degrau_aplicavel(HOJE + timedelta(days=1), _venc(10), {"d+7"}) is None


def test_progressao_completa_da_regua():
    venc = HOJE  # vence "hoje" na referência; simulamos o tempo passando
    enviados: set[str] = set()
    esperado = {2: None, 1: "d+1", 7: "d+7", 15: "d+15", 16: "escalado_advogado"}
    # d-3 antes do vencimento
    assert degrau_aplicavel(venc - timedelta(days=2), venc, enviados) == "d-3"
    enviados.add("d-3")
    for dias, deg in esperado.items():
        if dias == 2:
            continue
        got = degrau_aplicavel(venc + timedelta(days=dias), venc, enviados)
        assert got == deg, f"dia +{dias}: esperado {deg}, obtido {got}"
        if deg:
            enviados.add(deg)
    # Depois da escalada, silêncio permanente.
    assert degrau_aplicavel(venc + timedelta(days=60), venc, enviados) is None


# ── Template ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("degrau", ["d-3", "d+1", "d+7", "d+15"])
def test_template_cordial_identifica_parcela(degrau):
    assunto, corpo = montar_email_cobranca(
        degrau, "Honorários — parcela 2/5", 1234.56, date(2026, 7, 20),
    )
    assert assunto.startswith("[De Paula Teixeira Advogados]")
    assert "Honorários — parcela 2/5" in corpo
    assert "R$ 1.234,56" in corpo
    assert "20/07/2026" in corpo
    # Orientação sobre pagamento já efetuado + assinatura automática.
    assert "já tenha sido efetuado" in corpo
    assert ASSINATURA_AUTOMATICA in corpo
    # Cordialidade e canais: sem WhatsApp, sem tom ameaçador.
    assert "whatsapp" not in corpo.lower()
    assert "Prezado(a) cliente" in corpo


def test_template_d3_e_lembrete_a_vencer():
    assunto, corpo = montar_email_cobranca("d-3", "Parcela", 100.0,
                                           date(2026, 7, 14))
    assert "Lembrete" in assunto
    assert "vence em" in corpo


def test_template_d15_escala_firmeza_sem_perder_cordialidade():
    assunto, corpo = montar_email_cobranca("d+15", "Parcela", 100.0,
                                           date(2026, 6, 1))
    assert "atenção" in assunto.lower()
    assert "prioridade" in corpo
    assert "Atenciosamente" in corpo
