"""Regressões da auditoria financeira E2E de 02/09/2026.

Cobrem invariantes de validação e normalização que não podem regredir
silenciosamente, sem exigir acesso a banco de produção.
"""
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.routers.despesas import DespesaCreate, DespesaUpdate, _normalizar_baixa
from app.routers.office_contracts import ContractCreate
from app.routers.partner_withdrawals import WithdrawalCreate
from app.routers.pix import PixCobrancaIn, gerar_brcode
from app.schemas.fee import FeePaymentCreate, FeeUpdate


def test_fee_update_recusa_valor_negativo_e_campos_fantasmas():
    with pytest.raises(ValidationError):
        FeeUpdate(valor=Decimal("-0.01"))
    with pytest.raises(ValidationError):
        FeeUpdate(valor=Decimal("10.00"), campo_inexistente="x")


def test_pagamento_exige_valor_positivo_e_forma_controlada():
    base = {
        "valor": Decimal("10.00"),
        "data_pagamento": date(2026, 9, 2),
    }
    for forma in ("pix", "transferencia", "dinheiro", "cartao", "boleto", "outro", None):
        assert FeePaymentCreate(**base, forma=forma).valor == Decimal("10.00")

    with pytest.raises(ValidationError):
        FeePaymentCreate(**base, forma="cripto")
    with pytest.raises(ValidationError):
        FeePaymentCreate(**base, valor=Decimal("0"))
    with pytest.raises(ValidationError):
        FeePaymentCreate(**base, forma_pagamento="pix")


def test_despesa_exige_valor_positivo_status_e_competencia_validos():
    base = {
        "categoria": "tecnologia",
        "descricao": "Serviço",
        "valor": Decimal("100.00"),
        "competencia": "2026-09",
    }
    assert DespesaCreate(**base).valor == Decimal("100.00")

    for patch in (
        {**base, "valor": Decimal("0")},
        {**base, "status": "baixado"},
        {**base, "competencia": "2026-13"},
    ):
        with pytest.raises(ValidationError):
            DespesaCreate(**patch)

    with pytest.raises(ValidationError):
        DespesaUpdate(campo_inexistente="silencioso")


def test_despesa_normaliza_data_de_baixa_no_backend():
    hoje = date.today()
    assert _normalizar_baixa({"status": "pago"})["pago_em"] == hoje
    assert _normalizar_baixa({"status": "pendente"}, status_atual="pago")["pago_em"] is None
    assert _normalizar_baixa({"status": "cancelado"}, status_atual="pago")["pago_em"] is None

    with pytest.raises(HTTPException) as exc:
        _normalizar_baixa(
            {"status": "pendente", "pago_em": date(2026, 9, 2)},
            status_atual="pendente",
        )
    assert exc.value.status_code == 422


def test_contrato_recusa_valor_negativo_e_vigencia_invertida():
    with pytest.raises(ValidationError):
        ContractCreate(
            title="Contrato",
            counterparty="Fornecedor",
            start_date=date(2026, 9, 10),
            end_date=date(2026, 9, 1),
        )
    with pytest.raises(ValidationError):
        ContractCreate(
            title="Contrato",
            counterparty="Fornecedor",
            start_date=date(2026, 9, 1),
            value=Decimal("-1.00"),
        )


def test_saque_recusa_bruto_nao_positivo_e_despesa_negativa():
    with pytest.raises(ValidationError):
        WithdrawalCreate(gross_value=Decimal("0"))
    with pytest.raises(ValidationError):
        WithdrawalCreate(
            gross_value=Decimal("100.00"),
            case_expenses=Decimal("-0.01"),
        )


def test_pix_recusa_valor_nao_positivo_e_payload_extra():
    with pytest.raises(ValidationError):
        PixCobrancaIn(
            chave="teste@example.com",
            nome="Escritorio",
            cidade="Betim",
            valor=Decimal("0"),
        )
    with pytest.raises(ValidationError):
        PixCobrancaIn(
            chave="teste@example.com",
            nome="Escritorio",
            cidade="Betim",
            segredo="nao-aceitar",
        )


def test_brcode_decimal_preserva_centavos_e_crc():
    codigo = gerar_brcode(
        chave="teste@example.com",
        nome="Escritorio",
        cidade="Betim",
        valor=Decimal("123.45"),
        txid="ABC123",
    )
    assert "5406123.45" in codigo
    assert codigo[-8:-4] == "6304"
    assert len(codigo[-4:]) == 4