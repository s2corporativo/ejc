"""Cálculo de prazos processuais/administrativos (Fase 5) — funções puras."""
from datetime import date

from app.services.deadline_calculator import (
    calcular_pascoa,
    feriados_moveis,
    eh_feriado,
    eh_dia_util,
    prazo_dias_uteis,
    prazo_dias_corridos,
    calcular_prescricao,
)


def test_pascoa_gauss():
    assert calcular_pascoa(2024) == date(2024, 3, 31)
    assert calcular_pascoa(2025) == date(2025, 4, 20)
    assert calcular_pascoa(2026) == date(2026, 4, 5)


def test_feriados_moveis_2025():
    mov = feriados_moveis(2025)
    assert date(2025, 3, 3) in mov   # Segunda de Carnaval (Páscoa - 48)
    assert date(2025, 4, 18) in mov  # Sexta-feira Santa (Páscoa - 2)
    assert date(2025, 6, 19) in mov  # Corpus Christi (Páscoa + 60)


def test_eh_feriado_fixos_e_moveis():
    assert eh_feriado(date(2025, 12, 25)) is True   # Natal
    assert eh_feriado(date(2025, 4, 21)) is True    # Tiradentes
    assert eh_feriado(date(2025, 4, 18)) is True     # Sexta Santa (móvel)
    assert eh_feriado(date(2025, 6, 10)) is False    # terça comum


def test_eh_dia_util():
    assert eh_dia_util(date(2025, 6, 7)) is False    # sábado
    assert eh_dia_util(date(2025, 6, 8)) is False    # domingo
    assert eh_dia_util(date(2025, 6, 10)) is True     # terça comum
    assert eh_dia_util(date(2025, 12, 25)) is False  # Natal


def test_prazo_dias_uteis_exclui_inicio_e_fds():
    # Início seg 02/06/2025; 5 dias úteis (pula sáb/dom) → seg 09/06/2025
    assert prazo_dias_uteis(date(2025, 6, 2), 5) == date(2025, 6, 9)


def test_prazo_dias_corridos_prorroga_para_util():
    # 02/06 + 20 corridos = 22/06 (domingo) → prorroga p/ 23/06 (segunda)
    assert prazo_dias_corridos(date(2025, 6, 2), 20) == date(2025, 6, 23)


def test_prazo_em_dobro_equivale_ao_dobro_de_dias():
    # Prazo em dobro (CPC 183/229): dobra a CONTAGEM de dias úteis.
    inicio = date(2025, 6, 2)
    assert (prazo_dias_uteis(inicio, 5, em_dobro=True)
            == prazo_dias_uteis(inicio, 10))


def test_prazo_em_dobro_data_concreta():
    # Início seg 02/06/2025; 5 úteis = 09/06; em dobro (10 úteis) = 16/06.
    assert prazo_dias_uteis(date(2025, 6, 2), 5, em_dobro=True) == date(2025, 6, 16)


def test_prazo_em_dobro_default_desligado():
    # em_dobro=False (default) NÃO altera o resultado histórico.
    assert prazo_dias_uteis(date(2025, 6, 2), 5) == date(2025, 6, 9)


def test_calcular_prescricao_tabela():
    r = calcular_prescricao("reparacao_civil", date(2020, 1, 15))
    assert r["data_limite"] == date(2023, 1, 15)        # 3 anos
    assert "206" in r["base_legal"]
    assert calcular_prescricao("pretensao_geral", date(2020, 1, 15))["data_limite"] == date(2030, 1, 15)
    assert calcular_prescricao("inexistente", date(2020, 1, 1)) is None


# ── PRZ-03 (issue #1080): recesso forense parcial não afeta prazo não judicial ─

def test_recesso_parcial_nao_afeta_prazo_administrativo():
    """Prazo administrativo em dias úteis (Lei 9.784 art. 59) NÃO sofre o
    recesso forense parcial 20/12–06/01 — ele é próprio do Poder Judiciário
    (Lei 5.010/1966 art. 62, I; Res. CNJ 241/2016 art. 1º).
    Início seg 15/12/2025; 10 dias úteis sem recesso → qua 30/12/2025."""
    assert prazo_dias_uteis(date(2025, 12, 15), 10, forense=False) == date(2025, 12, 30)


def test_recesso_parcial_continua_afetando_prazo_judicial():
    """Prazo judicial em dias úteis (default) CONTINUA suspendendo no recesso
    parcial 20/12–06/01 — comportamento histórico preservado."""
    assert prazo_dias_uteis(date(2025, 12, 15), 10, forense=True) == date(2026, 1, 14)
    # default = judicial: mesmo resultado sem passar o parâmetro
    assert prazo_dias_uteis(date(2025, 12, 15), 10) == date(2026, 1, 14)


def test_eh_dia_util_recesso_parcial_controlavel():
    """eh_dia_util dentro do recesso parcial responde ao parâmetro forense."""
    dentro = date(2025, 12, 24)   # quarta dentro do recesso 20/12–06/01
    assert eh_dia_util(dentro, forense=True) is False
    assert eh_dia_util(dentro, forense=False) is True
