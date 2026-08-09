from datetime import date

import pytest

from app.services.deadline_calculator import (
    calcular_prazo_djen,
    data_publicacao_djen,
    regime_processual_por_area,
    termo_inicial_djen,
)


def test_djen_separa_disponibilizacao_publicacao_e_termo_inicial():
    # Qua 21/01/2026 -> publicação qui 22 -> termo inicial sex 23.
    disp = date(2026, 1, 21)
    pub = data_publicacao_djen(disp)
    termo = termo_inicial_djen(pub)

    assert pub == date(2026, 1, 22)
    assert termo == date(2026, 1, 23)


def test_civel_um_dia_usa_primeiro_util_apos_publicacao():
    calculo = calcular_prazo_djen(date(2026, 1, 21), 1, "civel")

    assert calculo["data_publicacao"] == date(2026, 1, 22)
    assert calculo["termo_inicial"] == date(2026, 1, 23)
    assert calculo["data_vencimento"] == date(2026, 1, 23)


def test_civel_travessa_recesso_20_dezembro_a_20_janeiro():
    # Disponibilização qui 18/12/2025 -> publicação sex 19/12. O primeiro dia
    # de contagem seria 22/12, mas o curso está suspenso até 20/01 inclusive.
    calculo = calcular_prazo_djen(date(2025, 12, 18), 1, "civel")

    assert calculo["data_publicacao"] == date(2025, 12, 19)
    assert calculo["termo_inicial"] == date(2026, 1, 21)
    assert calculo["data_vencimento"] == date(2026, 1, 21)


def test_trabalhista_tambem_aplica_recesso_integral():
    calculo = calcular_prazo_djen(date(2025, 12, 18), 2, "trabalhista")

    assert calculo["termo_inicial"] == date(2026, 1, 21)
    assert calculo["data_vencimento"] == date(2026, 1, 22)
    assert "CLT" in calculo["modo"]


def test_penal_e_continuo_e_prorroga_termo_final_nao_util():
    # Disponibilização seg 02/02 -> publicação ter 03/02 -> termo qua 04/02.
    # 4 dias contínuos: 04, 05, 06, 07(sáb). O termo final é prorrogado p/ 09/02.
    calculo = calcular_prazo_djen(date(2026, 2, 2), 4, "penal")

    assert calculo["data_publicacao"] == date(2026, 2, 3)
    assert calculo["termo_inicial"] == date(2026, 2, 4)
    assert calculo["data_vencimento"] == date(2026, 2, 9)
    assert "CPP" in calculo["modo"]


def test_penal_recesso_suspende_curso_salvo_excecao_explicitada():
    normal = calcular_prazo_djen(date(2025, 12, 18), 2, "penal")
    excecao = calcular_prazo_djen(
        date(2025, 12, 18),
        2,
        "penal",
        excecao_recesso_penal=True,
    )

    assert normal["termo_inicial"] == date(2026, 1, 21)
    assert normal["data_vencimento"] == date(2026, 1, 22)
    # Na exceção legal ao art. 798-A, a contagem não congela no recesso.
    assert excecao["termo_inicial"] == date(2025, 12, 22)
    assert excecao["data_vencimento"] == date(2025, 12, 23)


def test_area_criminal_deriva_penal_e_eleitoral_falha_fechado():
    assert regime_processual_por_area("criminal") == "penal"
    assert regime_processual_por_area("trabalhista") == "trabalhista"
    assert regime_processual_por_area("civil") == "civel"
    assert regime_processual_por_area("eleitoral") is None
    assert regime_processual_por_area(None) is None


def test_regime_invalido_nunca_e_convertido_silenciosamente_para_civil():
    with pytest.raises(ValueError, match="regime processual"):
        calcular_prazo_djen(date(2026, 2, 2), 5, "eleitoral")  # type: ignore[arg-type]
