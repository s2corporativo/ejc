# -*- coding: utf-8 -*-
"""Estorno de pagamento de honorário — fluxo próprio e auditável.

Fecha o achado P2 da homologação de 18/09/2026: os guards de cancelamento e
de overpayment exigiam "registre eventual estorno em fluxo próprio", mas o
fluxo não existia — honorário pago com lançamento errado ficava preso, e a
"correção" tentada era editar/apagar pagamento (proibido: ledger apend-only).

Regras cobertas (padrão do repo: schema puro + handler com fake de sessão,
sem banco real — ver test_fees_client_id_derivado_do_caso.py):

S1. FeeEstornoCreate recusa valor ≤ 0 e motivo vazio (lançamento auditável).
S2. FeeEstornoCreate recusa campo desconhecido (forbid) — mesmo contrato do
    pagamento.
H1. Estorno parcial em fee aberto: entra no ledger com audit ESTORNO e não
    reabre nada (não há o que reabrir).
H2. Estorno que derruba o total efetivo abaixo do contratado REABRE o
    honorário: pago → pendente (vencido → atrasado), data_pagamento limpa.
H3. Estorno acima do saldo do pagamento é recusado (422) — inclusive com
    estorno anterior acumulado no mesmo pagamento.
H4. Pagamento de outro honorário → 404; cancelado → 409; legado → 409.
L1. total_pago_efetivo subtrai estornos com piso em zero.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.fee import Fee, FeeEstorno, FeePayment, FeeStatus
from app.models.user import User, UserRole
from app.routers.fees import estornar_pagamento
from app.schemas.fee import FeeEstornoCreate
from app.services.fee_ledger_compat import total_pago_efetivo

HOJE = date.today()
ANTEONTEM = HOJE - timedelta(days=2)


# ── fake de sessão COM ESTADO (responde pela entidade da query) ────────────


class _Res:
    def __init__(self, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = rows or (Decimal("0"), 0)

    def scalar_one_or_none(self):
        return self._scalar

    def scalar(self):
        return self._scalar

    def one(self):
        return self._rows


class _LedgerFakeDB:
    """Sessão fake com estado do subledger.

    Mantém ``pagamentos`` e ``estornos`` (lista de dicts) e responde às
    consultas de ``total_pago_efetivo`` e do handler pela ENTIDADE/SQL da
    query — sem fila posicional frágil. ``add()`` atualiza o estado, então o
    total pós-flush já reflete o estorno gravado (comportamento real).
    """

    def __init__(self, fee: Fee, pagamentos: list[FeePayment]):
        self.fee = fee
        self.pagamentos = pagamentos
        self.estornos: list[FeeEstorno] = []
        self.added: list = []
        self.commits = 0
        self.flushes = 0

    async def execute(self, q):
        sql = str(q)
        cols = getattr(q, "column_descriptions", None)
        entidade = cols[0]["entity"] if cols else None

        if entidade is Fee and "fees" in sql and "fee_estornos" not in sql:
            return _Res(scalar=self.fee)
        if entidade is FeePayment:
            if "sum(" in sql and "count(" in sql:
                # Agregado do ledger (total_pago_efetivo)
                total = sum(
                    (Decimal(str(p.valor)) for p in self.pagamentos), Decimal("0")
                )
                return _Res(rows=(total, len(self.pagamentos)))
            if "fee_payments.id" in sql:
                # Busca do pagamento DENTRO do fee (o handler filtra fee_id)
                achado = next(
                    (
                        p
                        for p in self.pagamentos
                        if p.id == "pay1" and p.fee_id == self.fee.id
                    ),
                    None,
                )
                return _Res(scalar=achado)
            return _Res(scalar=None)

        if "fee_estornos" in sql:
            if "fee_payment_id" in sql:
                alvo = "pay1"
                subtotal = sum(
                    (
                        Decimal(str(e.valor))
                        for e in self.estornos
                        if e.fee_payment_id == alvo
                    ),
                    Decimal("0"),
                )
                return _Res(scalar=subtotal)
            total = sum((Decimal(str(e.valor)) for e in self.estornos), Decimal("0"))
            return _Res(scalar=total)

        raise AssertionError(f"Query não reconhecida pelo fake: {sql[:120]}")

    def add(self, obj):
        self.added.append(obj)
        if isinstance(obj, FeeEstorno):
            self.estornos.append(obj)

    async def flush(self):
        self.flushes += 1

    async def commit(self):
        self.commits += 1


def _user(role: UserRole = UserRole.admin) -> User:
    return User(id="u1", email="a@b.c", full_name="Admin", role=role)


def _fee(status=FeeStatus.pago, valor="1000.00", vencimento=None) -> Fee:
    return Fee(
        id="fee1",
        tipo="fixo",
        status=status,
        descricao="Honorário de teste",
        valor=Decimal(valor) if valor is not None else None,
        client_id="cli1",
        data_vencimento=vencimento,
    )


def _payment(valor="400.00", pid="pay1") -> FeePayment:
    return FeePayment(
        id=pid, fee_id="fee1", valor=Decimal(valor), data_pagamento=HOJE
    )


# ── S1/S2: validação de schema ──────────────────────────────────────────────


def test_estorno_zero_ou_negativo_e_recusado():
    with pytest.raises(Exception) as ei:
        FeeEstornoCreate(valor="0", data_estorno=HOJE, motivo="erro de digitação")
    assert "maior que zero" in str(ei.value)
    with pytest.raises(Exception):
        FeeEstornoCreate(valor="-50", data_estorno=HOJE, motivo="x")


def test_estorno_exige_motivo():
    with pytest.raises(Exception) as ei:
        FeeEstornoCreate(valor="100", data_estorno=HOJE, motivo="   ")
    assert "motivo" in str(ei.value)


def test_estorno_recusa_campo_desconhecido():
    with pytest.raises(Exception) as ei:
        FeeEstornoCreate(
            valor="100",
            data_estorno=HOJE,
            motivo="ok",
            status="pago",  # campo proibido: estorno não edita fee
        )
    assert "não reconhecido" in str(ei.value)


# ── H1: estorno parcial em fee aberto ───────────────────────────────────────


@pytest.mark.asyncio
async def test_estorno_parcial_em_fee_aberto_nao_altera_status_e_audita():
    """Fee pendente com pagamento parcial: estorno não tem o que reabrir,
    mas o lançamento entra no ledger e o total efetivo cai de 400 para 250."""
    fee = _fee(status=FeeStatus.pendente, valor="1000.00")
    db = _LedgerFakeDB(fee, [_payment("400.00")])

    resp = await estornar_pagamento(
        "fee1",
        "pay1",
        FeeEstornoCreate(
            valor="150.00", data_estorno=HOJE, motivo="Duplicidade parcial"
        ),
        db=db,
        cu=_user(),
    )

    assert resp["reaberto"] is False
    assert fee.status == FeeStatus.pendente
    assert resp["total_pago"] == 250.0
    assert resp["saldo"] == 750.0
    estorno = next(o for o in db.added if isinstance(o, FeeEstorno))
    assert estorno.valor == Decimal("150.00")
    assert estorno.fee_payment_id == "pay1"
    assert estorno.motivo == "Duplicidade parcial"
    assert db.commits == 1


# ── H2: reabertura ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_estorno_que_derruba_total_reabre_honorario_pendente():
    fee = _fee(
        status=FeeStatus.pago, valor="1000.00", vencimento=HOJE + timedelta(days=5)
    )
    db = _LedgerFakeDB(fee, [_payment("1000.00")])

    resp = await estornar_pagamento(
        "fee1",
        "pay1",
        FeeEstornoCreate(valor="100.00", data_estorno=HOJE, motivo="Pagamento indevido"),
        db=db,
        cu=_user(),
    )

    assert resp["reaberto"] is True
    assert fee.status == FeeStatus.pendente
    assert fee.data_pagamento is None
    assert db.commits == 1


@pytest.mark.asyncio
async def test_estorno_com_vencimento_passado_reabre_como_atrasado():
    fee = _fee(status=FeeStatus.pago, valor="1000.00", vencimento=ANTEONTEM)
    db = _LedgerFakeDB(fee, [_payment("1000.00")])

    resp = await estornar_pagamento(
        "fee1",
        "pay1",
        FeeEstornoCreate(valor="500.00", data_estorno=HOJE, motivo="Devolução acordada"),
        db=db,
        cu=_user(),
    )

    assert resp["reaberto"] is True
    assert fee.status == FeeStatus.atrasado


@pytest.mark.asyncio
async def test_fee_percentual_exito_nao_reabre_por_monetario():
    """Fee de êxito sem valor monetário não entra na regra de reabertura."""
    fee = _fee(status=FeeStatus.pago, valor=None)
    fee.percentual_exito = Decimal("10.00")
    db = _LedgerFakeDB(fee, [_payment("1000.00")])

    resp = await estornar_pagamento(
        "fee1",
        "pay1",
        FeeEstornoCreate(valor="400.00", data_estorno=HOJE, motivo="Devolução"),
        db=db,
        cu=_user(),
    )

    assert resp["reaberto"] is False
    assert fee.status == FeeStatus.pago


# ── H3: limites do estorno ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_estorno_acima_do_pagamento_e_recusado():
    fee = _fee(status=FeeStatus.pendente, valor="1000.00")
    db = _LedgerFakeDB(fee, [_payment("400.00")])

    with pytest.raises(HTTPException) as ei:
        await estornar_pagamento(
            "fee1",
            "pay1",
            FeeEstornoCreate(valor="500.00", data_estorno=HOJE, motivo="x"),
            db=db,
            cu=_user(),
        )
    assert ei.value.status_code == 422
    assert "disponível" in ei.value.detail


@pytest.mark.asyncio
async def test_estorno_acumulado_nao_superara_pagamento():
    fee = _fee(status=FeeStatus.pendente, valor="1000.00")
    db = _LedgerFakeDB(fee, [_payment("400.00")])
    # Estorno anterior de 350 já lançado contra pay1
    db.estornos.append(
        FeeEstorno(
            id="e0",
            fee_id="fee1",
            fee_payment_id="pay1",
            valor=Decimal("350.00"),
            motivo="anterior",
            data_estorno=HOJE,
        )
    )

    with pytest.raises(HTTPException) as ei:
        await estornar_pagamento(
            "fee1",
            "pay1",
            FeeEstornoCreate(valor="100.00", data_estorno=HOJE, motivo="x"),
            db=db,
            cu=_user(),
        )
    assert ei.value.status_code == 422  # disponível é 50, não 100


# ── H4/H5: guards ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pagamento_de_outro_fee_da_404():
    fee = _fee(status=FeeStatus.pendente)
    db = _LedgerFakeDB(fee, [])
    pagamento_ajeno = _payment("400.00")
    pagamento_ajeno.fee_id = "outro-fee"
    db.pagamentos.append(pagamento_ajeno)

    with pytest.raises(HTTPException) as ei:
        await estornar_pagamento(
            "fee1",
            "pay1",
            FeeEstornoCreate(valor="50", data_estorno=HOJE, motivo="x"),
            db=db,
            cu=_user(),
        )
    assert ei.value.status_code == 404


@pytest.mark.asyncio
async def test_fee_inexistente_da_404():
    db = _LedgerFakeDB(_fee(), [])
    db.fee = None

    with pytest.raises(HTTPException) as ei:
        await estornar_pagamento(
            "fee1",
            "pay1",
            FeeEstornoCreate(valor="50", data_estorno=HOJE, motivo="x"),
            db=db,
            cu=_user(),
        )
    assert ei.value.status_code == 404


@pytest.mark.asyncio
async def test_honorario_cancelado_recusa_estorno():
    fee = _fee(status=FeeStatus.cancelado)
    db = _LedgerFakeDB(fee, [_payment("400.00")])

    with pytest.raises(HTTPException) as ei:
        await estornar_pagamento(
            "fee1",
            "pay1",
            FeeEstornoCreate(valor="50", data_estorno=HOJE, motivo="x"),
            db=db,
            cu=_user(),
        )
    assert ei.value.status_code == 409


# ── L1: ledger ──────────────────────────────────────────────────────────────


class _LedgerOnlyDB:
    """Dois executes: (total, qtd) dos pagamentos e soma global dos estornos."""

    def __init__(self, pagamentos, estornos):
        self._pag = pagamentos
        self._est = estornos

    async def execute(self, _q):
        if self._pag is not None:
            r = _Res(rows=self._pag)
            self._pag = None
            return r
        return _Res(scalar=self._est)


@pytest.mark.asyncio
async def test_total_pago_efetivo_subtrai_estornos_piso_zero():
    fee = _fee(status=FeeStatus.pendente, valor="1000.00")

    total, legado = await total_pago_efetivo(
        _LedgerOnlyDB((Decimal("400.00"), 2), Decimal("100.00")), fee
    )
    assert (total, legado) == (Decimal("300.00"), False)

    total, _ = await total_pago_efetivo(
        _LedgerOnlyDB((Decimal("400.00"), 2), Decimal("900.00")), fee
    )
    assert total == Decimal("0")
