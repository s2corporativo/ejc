"""Contrato de admissão integrado ao financeiro sem liberar mutação genérica."""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.client import Client, ClientTipo
from app.models.fee import Fee, FeeStatus, FeeTipo
from app.services import geracao_documental_cliente as gdc


class _Result:
    def __init__(self, value=None):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeDB:
    def __init__(self, results):
        self.results = list(results)
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


def _usuario(role="advogado"):
    return SimpleNamespace(
        id="usr-1",
        full_name="Advogado Teste",
        oab_number="123456",
        role=SimpleNamespace(value=role),
    )


def test_contrato_recebe_valor_exito_e_forma_pagamento():
    texto = gdc._contrato_cliente(
        _cliente(),
        "Advogado Teste",
        "Civil",
        None,
        valor_contratual=3500,
        percentual_exito=20,
        forma_pagamento="entrada + 5 parcelas",
    )
    assert "R$ 3.500,00" in texto
    assert "20%" in texto
    assert "entrada + 5 parcelas" in texto


@pytest.mark.asyncio
async def test_sync_contrato_cria_fee_pendente_limitado_ao_cliente(monkeypatch):
    db = _FakeDB([None])

    async def _audit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(gdc, "criar_audit_log", _audit)
    res = await gdc._sincronizar_financeiro_contrato(
        db,
        _cliente(),
        _usuario("advogado"),
        valor_contratual=3500,
        percentual_exito=20,
        forma_pagamento="entrada + 5 parcelas",
        contrato_doc_id="doc-1",
    )

    fee = next(obj for obj in db.added if isinstance(obj, Fee))
    assert res["status"] == "sincronizado"
    assert fee.client_id == "cli-fin-1"
    assert fee.case_id is None
    assert fee.status == FeeStatus.pendente
    assert fee.tipo == FeeTipo.misto
    assert fee.valor == Decimal("3500.00")
    assert fee.percentual_exito == Decimal("20.00")
    assert "entrada + 5 parcelas" in fee.observacoes


@pytest.mark.asyncio
async def test_sync_bloqueia_mudanca_quando_ja_ha_recebimento():
    existente = Fee(
        id="fee-1",
        tipo=FeeTipo.fixo,
        status=FeeStatus.pendente,
        descricao=gdc._FEE_CONTRATO_DESCRICAO,
        valor=Decimal("1000.00"),
        client_id="cli-fin-1",
        case_id=None,
        observacoes=(
            gdc._FEE_CONTRATO_MARCADOR
            + "\nDocumento origem: doc-antigo.\nForma de pagamento: à vista."
        ),
    )
    db = _FakeDB([existente, "payment-1"])

    with pytest.raises(HTTPException) as exc:
        await gdc._sincronizar_financeiro_contrato(
            db,
            _cliente(),
            _usuario("advogado"),
            valor_contratual=2000,
            percentual_exito=None,
            forma_pagamento="2 parcelas",
            contrato_doc_id="doc-novo",
        )
    assert exc.value.status_code == 409
    assert "já possui recebimentos" in str(exc.value.detail)
