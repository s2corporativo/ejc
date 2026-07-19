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


def test_registros_locais_curados_tem_fonte_e_vigencia():
    # Curadoria 2026-07-18 (MG/BH): todo registro local exige fonte + vigência
    # (a validação fail-fast do módulo já derrubaria o import sem isso).
    assert set(cal.FERIADOS_LOCAIS) == {"TJMG", "TRT3"}
    assert set(cal.SUSPENSOES_TRIBUNAL) == {"TJMG", "TRT3"}
    for regs in list(cal.FERIADOS_LOCAIS.values()) + list(cal.SUSPENSOES_TRIBUNAL.values()):
        assert regs  # curadoria populada
        for reg in regs:
            assert reg.get("fonte"), reg
            assert reg.get("vigencia"), reg
            # Fonte precisa citar norma com número/ano ou página oficial.
            assert any(tok in reg["fonte"] for tok in
                       ("/1967", "/2004", "/PR/2026", "109, de 12/08/2025",
                        "991, de 03/11/2025")), reg
    # Tribunal sem curadoria continua vazio (nada inventado).
    assert cal.datas_feriados_locais("TJSP") == frozenset()
    assert cal.datas_suspensoes_tribunal("TRT2") == frozenset()


def test_feriados_locais_bh_curados():
    # Lei municipal de BH 1.327/1967: Assunção (15/08) e Imaculada (08/12).
    tjmg = cal.datas_feriados_locais("TJMG")
    trt3 = cal.datas_feriados_locais("TRT3")
    for datas in (tjmg, trt3):
        assert date(2026, 8, 15) in datas
        assert date(2026, 12, 8) in datas
        assert date(2027, 12, 8) in datas


def test_suspensoes_tjmg_2026_curadas():
    # Portaria Conjunta 1798/PR/2026 + Resolução 458/2004 (Carnaval).
    dias = cal.datas_suspensoes_tribunal("TJMG")
    assert date(2026, 2, 18) in dias   # Quarta-feira de Cinzas
    assert date(2026, 4, 1) in dias    # Semana Santa (quarta)
    assert date(2026, 4, 2) in dias    # Semana Santa (quinta)
    assert date(2026, 4, 20) in dias   # ponte antes de Tiradentes
    assert date(2026, 10, 30) in dias  # Dia do Servidor Público
    assert date(2026, 12, 7) in dias   # ponte antes de 08/12 (BH)
    # TRT3 — RA 109/2025: Semana Santa 01–05/04/2026.
    assert date(2026, 4, 1) in cal.datas_suspensoes_tribunal("TRT3")
    assert date(2026, 4, 2) in cal.datas_suspensoes_tribunal("TRT3")


def test_feriado_local_afeta_somente_com_tribunal():
    # 08/12/2026 (terça): feriado municipal de BH (Lei 1.327/1967) — não útil
    # para o TJMG; SEM tribunal informado, comportamento nacional inalterado.
    d = date(2026, 12, 8)
    assert eh_dia_util(d) is True
    assert eh_dia_util(d, tribunal="TJMG") is False
    assert eh_dia_util(d, tribunal="TRT3") is False
    # Suspensão curada (20/04/2026, segunda) — idem.
    s = date(2026, 4, 20)
    assert eh_dia_util(s) is True
    assert eh_dia_util(s, tribunal="TJMG") is False
    assert eh_dia_util(s, tribunal="TRT3") is True  # não curada p/ TRT3
    # Tribunal sem curadoria ⇒ nada muda.
    assert eh_dia_util(d, tribunal="TJSP") is True


def test_prazo_dias_uteis_considera_curadoria_tjmg():
    # 5 dias úteis a partir de qui 03/12/2026: sem tribunal ⇒ 4,7,8,9,10/12
    # (vence 10/12); com TJMG, 07/12 (suspensão PC 1798) e 08/12 (Imaculada
    # BH) não contam ⇒ vence 14/12/2026 (segunda).
    inicio = date(2026, 12, 3)
    assert prazo_dias_uteis(inicio, 5) == date(2026, 12, 10)
    assert prazo_dias_uteis(inicio, 5, tribunal="TJMG") == date(2026, 12, 14)


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
