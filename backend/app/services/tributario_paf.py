"""Regra temporal do PAF federal após a LC 227/2026.

Fonte operacional para prazos de impugnação e recurso voluntário no rito do
Decreto 70.235/1972. Mantém a transição de 2026 e a suspensão processual do
art. 5º-A separadas do recesso forense: trata-se de processo administrativo
fiscal, não de prazo judicial.

A função calcula apenas o REGIME FEDERAL. Estados e municípios possuem rito
próprio e não podem herdar prazo por analogia.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.services.deadline_calculator import eh_dia_util, proximo_dia_util

LC227_VIGENCIA = date(2026, 1, 14)
TRANSICAO_ADI_RFB_2_ATE = date(2026, 3, 31)
VERSAO_REGRA_PAF = "2026-09-lc227"

FONTES_PAF = [
    "Decreto 70.235/1972 arts. 5º, 5º-A, 15 e 33, redação da LC 227/2026",
    "Lei Complementar 227/2026",
    "ADI RFB 2/2026 — regra de transição até 31/03/2026",
    "Receita Federal — Perguntas e Respostas Prazos Processuais LC 227/2026, atualização 13/03/2026",
]


def suspenso_paf_federal(dia: date) -> bool:
    """Suspensão do art. 5º-A com regra especial de entrada em vigor em 2026.

    Em 2026 a LC 227 entrou em vigor em 14/01: não há retroatividade para
    01-13/01/2026. A partir do fim de 2026 aplica-se integralmente 20/12-20/01.
    """
    if dia.year == 2026 and dia.month == 1:
        return 14 <= dia.day <= 20
    if dia.year >= 2026 and dia.month == 12:
        return dia.day >= 20
    if dia.year >= 2027 and dia.month == 1:
        return dia.day <= 20
    return False


def _prazo_corridos_processual(data_ciencia: date, dias: int) -> date:
    """Conta dias corridos excluindo a ciência, congelando suspensão do PAF."""
    atual = data_ciencia
    contados = 0
    while contados < dias:
        atual += timedelta(days=1)
        if suspenso_paf_federal(atual):
            continue
        contados += 1
    return proximo_dia_util(atual, forense=False)


def _prazo_uteis_processual(data_ciencia: date, dias: int) -> date:
    """Conta dias úteis excluindo a ciência e respeitando a suspensão do PAF."""
    atual = data_ciencia
    contados = 0
    while contados < dias:
        atual += timedelta(days=1)
        if suspenso_paf_federal(atual):
            continue
        if eh_dia_util(atual, forense=False):
            contados += 1
    return atual


def calcular_prazo_impugnacao_paf(data_ciencia: date) -> dict:
    """Calcula a regra federal aplicável pela data de ciência.

    - ciência anterior a 14/01/2026: regime anterior de 30 dias corridos; se o
      prazo ainda estava em curso, suspende 14-20/01/2026;
    - ciência de 14/01 a 31/03/2026: por segurança jurídica, considera o prazo
      que vencer por último entre 20 dias úteis e 30 dias corridos (ADI RFB 2);
    - ciência após 31/03/2026: 20 dias úteis.
    """
    if data_ciencia < LC227_VIGENCIA:
        vencimento = _prazo_corridos_processual(data_ciencia, 30)
        return {
            "criterio": "regime_anterior_30_corridos",
            "prazo": "30 dias corridos, com suspensão do art. 5º-A somente a partir de 14/01/2026 se incidente",
            "vencimento": vencimento,
            "componentes": {"30_dias_corridos": vencimento},
        }

    venc_20_uteis = _prazo_uteis_processual(data_ciencia, 20)
    if data_ciencia <= TRANSICAO_ADI_RFB_2_ATE:
        venc_30_corridos = _prazo_corridos_processual(data_ciencia, 30)
        vencimento = max(venc_20_uteis, venc_30_corridos)
        return {
            "criterio": "transicao_adi_rfb_2_2026_maior_vencimento",
            "prazo": "20 dias úteis ou 30 dias corridos, prevalecendo o vencimento posterior",
            "vencimento": vencimento,
            "componentes": {
                "20_dias_uteis": venc_20_uteis,
                "30_dias_corridos": venc_30_corridos,
            },
        }

    return {
        "criterio": "lc227_20_uteis",
        "prazo": "20 dias úteis",
        "vencimento": venc_20_uteis,
        "componentes": {"20_dias_uteis": venc_20_uteis},
    }
