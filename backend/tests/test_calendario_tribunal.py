"""Fase 2 — Calendário de tribunal versionado + recesso CPC art. 220.

Garante:
  • todo registro do calendário tem fonte e vigência (regra: nunca inventar);
  • centralização dos feriados nacionais SEM quebra (mesmo conjunto histórico);
  • sem dados locais cadastrados ⇒ comportamento IDÊNTICO ao anterior;
  • aplicar_recesso=True estende a suspensão até 20/01 (CPC art. 220) SOMENTE
    quando pedido (default False = retrocompatível);
  • prazos em dias corridos NÃO sofrem o recesso (decadenciais/administrativos).
"""
from datetime import date

from app.services import calendario_tribunal as cal
from app.services.deadline_calculator import (
    FERIADOS_FIXOS,
    eh_dia_util,
    prazo_dias_corridos,
    prazo_dias_uteis,
)


# ── Regra da casa: fonte e vigência obrigatórias em cada registro ────────────

def test_todos_registros_tem_fonte_e_vigencia():
    for reg in cal.FERIADOS_NACIONAIS + cal.FERIADOS_MOVEIS_INFO:
        assert reg.get("fonte"), reg
        assert reg.get("vigencia"), reg
    assert cal.RECESSO_ART_220["fonte"]
    assert cal.RECESSO_ART_220["vigencia"]


def test_tribunais_especificos_sao_estrutura_vazia_documentada():
    # Curadoria futura: nada inventado — estruturas nascem vazias.
    assert cal.FERIADOS_LOCAIS == {}
    assert cal.SUSPENSOES_TRIBUNAL == {}
    assert cal.datas_feriados_locais("TJMG") == frozenset()
    assert cal.datas_suspensoes_tribunal("TRT3") == frozenset()


def test_versao_calendario_metadados():
    v = cal.versao_calendario()
    assert v["versao"] == cal.CALENDARIO_VERSAO
    assert v["feriados_nacionais"] == len(cal.FERIADOS_NACIONAIS)
    assert "220" in v["recesso_art_220"]


# ── Centralização sem quebra ─────────────────────────────────────────────────

def test_feriados_nacionais_identicos_ao_conjunto_historico():
    historico = {
        (1, 1), (21, 4), (1, 5), (7, 9), (12, 10),
        (2, 11), (15, 11), (20, 11), (25, 12),
    }
    assert cal.feriados_fixos_nacionais() == historico
    assert FERIADOS_FIXOS == historico  # alias retrocompatível


def test_sem_dados_locais_comportamento_identico():
    # Mesmos resultados dos testes históricos do deadline_calculator.
    assert prazo_dias_uteis(date(2025, 6, 2), 5) == date(2025, 6, 9)
    assert prazo_dias_corridos(date(2025, 6, 2), 20) == date(2025, 6, 23)
    assert eh_dia_util(date(2025, 6, 10)) is True
    assert eh_dia_util(date(2025, 12, 25)) is False
    # Tribunal informado mas sem curadoria local ⇒ nada muda.
    assert prazo_dias_uteis(date(2025, 6, 2), 5, tribunal="TJMG") == date(2025, 6, 9)


# ── Recesso CPC art. 220 (20/12 a 20/01, inclusive) ──────────────────────────

def test_em_recesso_art220_janela_completa():
    assert cal.em_recesso_art220(date(2025, 12, 19)) is False
    assert cal.em_recesso_art220(date(2025, 12, 20)) is True
    assert cal.em_recesso_art220(date(2026, 1, 1)) is True
    assert cal.em_recesso_art220(date(2026, 1, 20)) is True
    assert cal.em_recesso_art220(date(2026, 1, 21)) is False


def test_eh_dia_util_aplicar_recesso_estende_ate_20_01():
    # 08/01/2026 (quinta): útil no comportamento histórico (recesso parcial
    # ia só até 06/01), NÃO útil com a suspensão integral do art. 220.
    d = date(2026, 1, 8)
    assert eh_dia_util(d) is True
    assert eh_dia_util(d, aplicar_recesso=True) is False


def test_prazo_dias_uteis_com_recesso_art220():
    inicio = date(2025, 12, 15)  # segunda-feira
    # Default (histórico): retoma a contagem em 07/01 ⇒ 10 úteis = 14/01/2026.
    assert prazo_dias_uteis(inicio, 10) == date(2026, 1, 14)
    # Art. 220 integral: retoma em 21/01 ⇒ 10 úteis = 28/01/2026.
    assert prazo_dias_uteis(inicio, 10, aplicar_recesso=True) == date(2026, 1, 28)


def test_recesso_nao_afeta_prazos_corridos():
    # Prazo administrativo em dias corridos atravessa o recesso normalmente
    # (Lei 9.784/99 — só prorroga o VENCIMENTO caindo em dia não útil).
    assert prazo_dias_corridos(date(2025, 12, 10), 20) == date(2025, 12, 30)
    # Decadencial (prorrogar_fim=False): nem prorrogação de vencimento.
    assert prazo_dias_corridos(date(2025, 12, 10), 20,
                               prorrogar_fim=False) == date(2025, 12, 30)
