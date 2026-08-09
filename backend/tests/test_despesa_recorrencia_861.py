from datetime import date

from app.services.despesa_service import _vencimento_na_competencia


def test_vencimento_dia_31_ajusta_para_ultimo_dia_de_fevereiro():
    assert _vencimento_na_competencia(date(2026, 1, 31), "2026-02") == date(
        2026, 2, 28
    )


def test_vencimento_dia_31_respeita_ano_bissexto():
    assert _vencimento_na_competencia(date(2027, 1, 31), "2028-02") == date(
        2028, 2, 29
    )


def test_modelo_sem_vencimento_nao_inventa_data():
    assert _vencimento_na_competencia(None, "2026-02") is None
