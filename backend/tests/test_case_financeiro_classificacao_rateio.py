from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.routers.cases import EncerrarCasoSimplesReq, RegistrarRecebimentoCasoReq
from app.schemas.case import CaseUpdate
from app.services.case_finance_service import calcular_rateio_recebimento


@pytest.mark.parametrize("classificacao", ["normal", "pro_bono", "causa_propria"])
def test_classificacoes_financeiras_validas(classificacao):
    assert CaseUpdate(classificacao_financeira=classificacao).classificacao_financeira == classificacao


def test_classificacao_financeira_invalida():
    with pytest.raises(ValidationError):
        CaseUpdate(classificacao_financeira="vip")


def test_valor_pleiteado_nao_aceita_negativo():
    with pytest.raises(ValidationError):
        CaseUpdate(valor_pleiteado=Decimal("-0.01"))


def test_rateio_padrao_50_50():
    r = calcular_rateio_recebimento("trabalhista", Decimal("1000.01"))
    assert r["percentual_advogado"] == Decimal("50.00")
    assert r["valor_advogado"] == Decimal("500.01")
    assert r["valor_escritorio"] == Decimal("500.00")
    assert r["regra"] == "rateio_50_50"


def test_area_civil_fica_integralmente_com_escritorio():
    r = calcular_rateio_recebimento("civil", Decimal("1000.01"))
    assert r["percentual_advogado"] == Decimal("0.00")
    assert r["valor_advogado"] == Decimal("0.00")
    assert r["valor_escritorio"] == Decimal("1000.01")
    assert r["regra"] == "institucional_integral_escritorio"


def test_encerramento_simples_exige_so_nome_e_valor():
    req = EncerrarCasoSimplesReq(cliente_nome="Cliente Teste", valor_recebido="123.45")
    assert req.cliente_nome == "Cliente Teste"
    assert req.valor_recebido == Decimal("123.45")
    with pytest.raises(ValidationError):
        EncerrarCasoSimplesReq(
            cliente_nome="Cliente Teste",
            valor_recebido="123.45",
            resultado="exito",
        )


def test_recebimento_deve_ser_positivo():
    with pytest.raises(ValidationError):
        RegistrarRecebimentoCasoReq(valor="0")


def test_consumidor_e_jec_ficam_integralmente_com_escritorio():
    consumidor = calcular_rateio_recebimento("consumidor", Decimal("800.00"))
    jec = calcular_rateio_recebimento("trabalhista", Decimal("800.00"), "Juizado Especial Cível de Betim")
    assert consumidor["valor_advogado"] == Decimal("0.00")
    assert consumidor["valor_escritorio"] == Decimal("800.00")
    assert jec["valor_advogado"] == Decimal("0.00")
    assert jec["valor_escritorio"] == Decimal("800.00")


@pytest.mark.asyncio
async def test_recebimento_flusha_pagamento_antes_do_rateio(monkeypatch):
    from types import SimpleNamespace
    from app.models.fee import CaseReceiptAllocation, Fee, FeePayment
    from app.services import case_finance_service as svc

    eventos = []

    class FakeDb:
        def add(self, obj):
            eventos.append(("add", type(obj).__name__))

        async def flush(self):
            eventos.append(("flush", None))

    async def audit_noop(*args, **kwargs):
        return None

    monkeypatch.setattr(svc, "criar_audit_log", audit_noop)
    db = FakeDb()
    case = SimpleNamespace(
        id="case-1",
        area="civil",
        vara=None,
        advogado_responsavel_id=None,
        client_id="client-1",
        numero_interno="DPT-2026-TESTE",
    )
    user = SimpleNamespace(id="user-1", role=SimpleNamespace(value="admin"))

    result = await svc.registrar_recebimento_caso(db, case, Decimal("100.00"), user)

    assert result["valor_escritorio"] == Decimal("100.00")
    assert eventos[:4] == [
        ("add", Fee.__name__),
        ("add", FeePayment.__name__),
        ("flush", None),
        ("add", CaseReceiptAllocation.__name__),
    ]
