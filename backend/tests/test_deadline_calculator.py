"""Cálculo de prazos processuais/administrativos (Fase 5) — funções puras."""
from datetime import date

from app.services.calc import constantes_legais  # noqa: F401 (garante import do pacote)
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


def test_calcular_prescricao_tabela():
    r = calcular_prescricao("reparacao_civil", date(2020, 1, 15))
    assert r["data_limite"] == date(2023, 1, 15)        # 3 anos
    assert "206" in r["base_legal"]
    assert calcular_prescricao("pretensao_geral", date(2020, 1, 15))["data_limite"] == date(2030, 1, 15)
    assert calcular_prescricao("inexistente", date(2020, 1, 1)) is None
