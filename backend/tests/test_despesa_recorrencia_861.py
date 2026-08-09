from datetime import date

from app.schemas.despesa import DespesaCreate, DespesaUpdate
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


def test_create_converte_datas_iso_para_date_antes_do_driver():
    payload = DespesaCreate.model_validate(
        {
            "categoria": "Software",
            "tipo": "fixo",
            "descricao": "Assinatura mensal",
            "valor": "199.90",
            "vencimento": "2026-08-15",
            "pago_em": "2026-08-10",
            "status": "pago",
            "competencia": "2026-08",
        }
    )

    dados = payload.model_dump(mode="python")
    assert dados["vencimento"] == date(2026, 8, 15)
    assert dados["pago_em"] == date(2026, 8, 10)
    assert isinstance(dados["vencimento"], date)
    assert isinstance(dados["pago_em"], date)


def test_patch_converte_data_iso_para_date_antes_do_driver():
    payload = DespesaUpdate.model_validate({"vencimento": "2026-09-01"})
    dados = payload.model_dump(exclude_unset=True, mode="python")

    assert dados == {"vencimento": date(2026, 9, 1)}
