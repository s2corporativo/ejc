"""Contrato de admissão integrado ao Financeiro com parcelamento determinístico."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.client import Client, ClientTipo
from app.models.fee import Fee, FeeStatus, FeeTipo
from app.services import geracao_documental_cliente as gdc


class _Scalars:
    def __init__(self, values):
        self.values = list(values or [])

    def all(self):
        return self.values


class _Result:
    def __init__(self, value=None):
        self.value = value

    def scalar_one_or_none(self):
        if isinstance(self.value, list):
            return self.value[0] if self.value else None
        return self.value

    def scalar(self):
        return self.value

    def scalars(self):
        return _Scalars(self.value if isinstance(self.value, list) else [])


class _FakeDB:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.added = []

    async def execute(self, _query):
        return _Result(self.results.pop(0) if self.results else None)

    def add(self, obj):
        self.added.append(obj)


def _cliente():
    return Client(
        id="cli-fin-1",
        tipo=ClientTipo.PF,
        nome="Maria Souza",
        profissao="empresária",
        logradouro="Rua Um",
        numero="10",
        bairro="Centro",
        cidade="Betim",
        estado="MG",
        cep="32600-000",
    )


def _usuario(role="socio"):
    return SimpleNamespace(
        id="usr-1",
        full_name="Advogado Teste",
        oab_number="123456",
        role=SimpleNamespace(value=role),
    )


def test_cronograma_entrada_mais_tres_parcelas_fecha_valor_exato():
    cronograma = gdc._cronograma_fixo(
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


def test_somar_meses_respeita_ultimo_dia():
    assert gdc._somar_meses(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert gdc._somar_meses(date(2026, 1, 31), 2) == date(2026, 3, 31)


def test_contrato_recebe_valor_exito_e_cronograma():
    cronograma = gdc._cronograma_fixo(
        Decimal("3500"),
        Decimal("500"),
        3,
        date(2026, 11, 10),
        data_entrada=date(2026, 10, 2),
    )
    forma = gdc._descricao_cronograma(cronograma, "PIX ou boleto")
    texto = gdc._contrato_cliente(
        _cliente(),
        "Advogado Teste",
        "Civil",
        None,
        valor_contratual=3500,
        percentual_exito=20,
        forma_pagamento=forma,
    )
    assert "R$ 3.500,00" in texto
    assert "20%" in texto
    assert "3 parcela(s) mensal(is)" in texto
    assert "10/11/2026" in texto


@pytest.mark.asyncio
async def test_advogado_preenche_minuta_sem_mutar_ledger():
    db = _FakeDB()
    res = await gdc._sincronizar_financeiro_contrato(
        db,
        _cliente(),
        _usuario("advogado"),
        valor_contratual=3500,
        entrada=500,
        numero_parcelas=3,
        percentual_exito=20,
        forma_pagamento="PIX",
        data_vencimento=date(2026, 11, 10),
        contrato_doc_id="doc-1",
    )
    assert res["status"] == "pendente_permissao"
    assert db.added == []


@pytest.mark.asyncio
async def test_socio_cria_entrada_parcelas_e_exito(monkeypatch):
    db = _FakeDB([[]])

    async def _audit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(gdc, "criar_audit_log", _audit)
    res = await gdc._sincronizar_financeiro_contrato(
        db,
        _cliente(),
        _usuario("socio"),
        valor_contratual=5000,
        entrada=1000,
        numero_parcelas=3,
        percentual_exito=20,
        forma_pagamento="PIX ou boleto",
        data_vencimento=date(2026, 11, 10),
        contrato_doc_id="doc-1",
    )

    fees = [obj for obj in db.added if isinstance(obj, Fee)]
    fixos = [fee for fee in fees if fee.tipo == FeeTipo.fixo]
    exitos = [fee for fee in fees if fee.tipo == FeeTipo.exito]
    assert res["status"] == "sincronizado"
    assert res["parcelas_criadas"] == 4
    assert [fee.valor for fee in fixos] == [
        Decimal("1000.00"),
        Decimal("1333.34"),
        Decimal("1333.33"),
        Decimal("1333.33"),
    ]
    assert [fee.data_vencimento for fee in fixos] == [
        date(2026, 10, 2),
        date(2026, 11, 10),
        date(2026, 12, 10),
        date(2027, 1, 10),
    ]
    assert len(exitos) == 1
    assert exitos[0].percentual_exito == Decimal("20.00")
    assert all(fee.client_id == "cli-fin-1" for fee in fees)
    assert all(fee.case_id is None for fee in fees)


@pytest.mark.asyncio
async def test_reemissao_preserva_recebido_e_recria_somente_saldo(monkeypatch):
    existente = Fee(
        id="fee-antigo",
        tipo=FeeTipo.fixo,
        status=FeeStatus.pendente,
        descricao=gdc._FEE_CONTRATO_DESCRICAO + " — Parcela 1/2",
        valor=Decimal("1000.00"),
        client_id="cli-fin-1",
        case_id=None,
        observacoes=(
            gdc._FEE_CONTRATO_MARCADOR
            + "\n[componente=fixo;item=parcela-1-de-2]"
        ),
    )
    # 1) histórico, 2) soma pagamentos, 3) soma estornos.
    db = _FakeDB([[existente], Decimal("200.00"), Decimal("0.00")])

    async def _audit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(gdc, "criar_audit_log", _audit)
    res = await gdc._sincronizar_financeiro_contrato(
        db,
        _cliente(),
        _usuario("socio"),
        valor_contratual=2000,
        entrada=None,
        numero_parcelas=2,
        percentual_exito=None,
        forma_pagamento=None,
        data_vencimento=date(2026, 11, 10),
        contrato_doc_id="doc-novo",
    )

    novos = [obj for obj in db.added if isinstance(obj, Fee)]
    assert existente.status == FeeStatus.cancelado
    assert res["valor_pago_preservado"] == 200.0
    assert [fee.valor for fee in novos] == [
        Decimal("900.00"),
        Decimal("900.00"),
    ]
    assert sum(fee.valor for fee in novos) == Decimal("1800.00")
