from datetime import date
from decimal import Decimal

from app.services.geracao_documental_cliente import (
    _cronograma_fixo,
    _descricao_cronograma,
    _somar_meses,
)


def test_cronograma_entrada_mais_tres_parcelas_fecha_valor_exato():
    cronograma = _cronograma_fixo(
        Decimal("5000.00"),
        Decimal("1000.00"),
        3,
        date(2026, 11, 10),
        data_entrada=date(2026, 10, 2),
    )

    assert [item["rotulo"] for item in cronograma] == [
        "Entrada",
        "Parcela 1/3",
        "Parcela 2/3",
        "Parcela 3/3",
    ]
    assert [item["valor"] for item in cronograma] == [
        Decimal("1000.00"),
        Decimal("1333.34"),
        Decimal("1333.33"),
        Decimal("1333.33"),
    ]
    assert sum(item["valor"] for item in cronograma) == Decimal("5000.00")
    assert [item["vencimento"] for item in cronograma[1:]] == [
        date(2026, 11, 10),
        date(2026, 12, 10),
        date(2027, 1, 10),
    ]


def test_centavo_residual_nao_some_no_parcelamento():
    cronograma = _cronograma_fixo(
        Decimal("100.00"),
        None,
        3,
        date(2026, 11, 30),
        data_entrada=date(2026, 10, 2),
    )
    assert [item["valor"] for item in cronograma] == [
        Decimal("33.34"),
        Decimal("33.33"),
        Decimal("33.33"),
    ]
    assert sum(item["valor"] for item in cronograma) == Decimal("100.00")


def test_somar_meses_respeita_ultimo_dia_do_mes():
    assert _somar_meses(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert _somar_meses(date(2026, 1, 31), 2) == date(2026, 3, 31)


def test_descricao_cronograma_reflete_entrada_parcelas_e_vencimento():
    cronograma = _cronograma_fixo(
        Decimal("5000.00"),
        Decimal("1000.00"),
        3,
        date(2026, 11, 10),
        data_entrada=date(2026, 10, 2),
    )
    texto = _descricao_cronograma(cronograma, "PIX ou boleto")
    assert "entrada de R$ 1.000,00" in texto
    assert "3 parcela(s) mensal(is)" in texto
    assert "10/11/2026" in texto
    assert "condição adicional: PIX ou boleto" in texto
