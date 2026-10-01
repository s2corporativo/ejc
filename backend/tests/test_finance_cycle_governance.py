from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4
import os

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine
from app.models.case import Case
from app.models.centro_custo import CentroCusto, CentroCustoCategoria, CentroCustoTipo
from app.models.fee import Fee, FeeEstorno, FeePayment, FeeStatus, FeeTipo
from app.models.user import User
from app.routers.financeiro_consolidado import (
    CommissionBatchIn,
    FinanceCloseIn,
    fechar_competencia_financeira,
    pagar_comissoes_em_lote,
)
from app.routers.partner_withdrawals import approve_withdrawal
from app.services.commission_service import (
    alocar_comissao_pagamento,
    registrar_ajuste_comissao,
    registrar_reversao_comissao_estorno,
)
from app.services.finance_governance import (
    competencia_de_data,
    exigir_competencia_aberta,
)


class _Scalar:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _GuardDB:
    def __init__(self, closed: bool):
        self.closed = closed

    async def execute(self, statement, params=None):
        return _Scalar("closed-id" if self.closed else None)


def test_competencia_de_data_e_deterministica():
    assert competencia_de_data(date(2026, 9, 30)) == "2026-09"
    assert competencia_de_data(datetime(2027, 1, 5, 10, 0)) == "2027-01"


@pytest.mark.asyncio
async def test_competencia_fechada_bloqueia_reescrita():
    with pytest.raises(HTTPException) as exc:
        await exigir_competencia_aberta(
            _GuardDB(True),
            "2026-09",
            "Alterar lançamento",
        )
    assert exc.value.status_code == 409
    assert "já está fechada" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_competencia_aberta_permite_mutacao():
    await exigir_competencia_aberta(
        _GuardDB(False),
        "2026-10",
        "Alterar lançamento",
    )


@pytest.mark.asyncio
async def test_ciclo_financeiro_governado_com_rollback():
    """Fluxo real do ledger em transação externa; nenhum dado de teste persiste."""
    if os.getenv("EJC_RUN_DB_TESTS") != "1":
        pytest.skip("Integração PostgreSQL habilitada com EJC_RUN_DB_TESTS=1")
    async with engine.connect() as conn:
        outer = await conn.begin()
        db = AsyncSession(
            bind=conn,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            caso = (
                await db.execute(
                    select(Case)
                    .where(
                        Case.deleted_at.is_(None),
                        Case.client_id.is_not(None),
                        Case.advogado_responsavel_id.is_not(None),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if not caso:
                pytest.skip("Base de teste sem caso apto ao ciclo financeiro")

            users = (
                await db.execute(select(User).where(User.deleted_at.is_(None)))
            ).scalars().all()
            gestor = next(
                (
                    u
                    for u in users
                    if getattr(u.role, "value", str(u.role))
                    in {"superadmin", "admin", "socio"}
                    and str(u.id) != str(caso.advogado_responsavel_id)
                ),
                None,
            )
            if not gestor:
                pytest.skip("Base de teste sem segundo gestor para segregação")

            # Despesa paga existe ANTES do recebimento: comissão deve usar base líquida.
            cc = CentroCusto(
                id=str(uuid4()),
                case_id=caso.id,
                tipo=CentroCustoTipo.despesa,
                categoria=CentroCustoCategoria.custas,
                valor=Decimal("100.00"),
                moeda="BRL",
                descricao="TESTE GOVERNANÇA ROLLBACK",
                data_lancamento=date.today(),
                data_pagamento=date.today(),
                pago=True,
                created_by=gestor.id,
            )
            db.add(cc)
            await db.flush()

            fid, pid = str(uuid4()), str(uuid4())
            fee = Fee(
                id=fid,
                tipo=FeeTipo.fixo,
                status=FeeStatus.pendente,
                descricao="TESTE CICLO FINANCEIRO ROLLBACK",
                valor=Decimal("1000.00"),
                client_id=caso.client_id,
                case_id=caso.id,
            )
            db.add(fee)
            await db.flush()
            payment = FeePayment(
                id=pid,
                fee_id=fid,
                valor=Decimal("1000.00"),
                data_pagamento=date.today(),
                forma="pix",
            )
            db.add(payment)
            await db.flush()

            alloc = await alocar_comissao_pagamento(db, caso, payment, gestor)
            assert alloc["base_liquida"] == Decimal("900.00")
            assert alloc["despesas_deduzidas"] == Decimal("100.00")
            wid = alloc["withdrawal_id"]
            assert wid

            # Estorno de 20% reverte proporcionalmente a comissão.
            eid = str(uuid4())
            db.add(
                FeeEstorno(
                    id=eid,
                    fee_id=fid,
                    fee_payment_id=pid,
                    valor=Decimal("200.00"),
                    motivo="teste rollback",
                    data_estorno=date.today(),
                )
            )
            await db.flush()
            reversal = await registrar_reversao_comissao_estorno(
                db,
                fee_payment_id=pid,
                fee_estorno_id=eid,
                valor_estorno=Decimal("200.00"),
                motivo="teste rollback",
                user=gestor,
            )
            assert Decimal(str(reversal["valor_advogado"])) < 0

            await approve_withdrawal(wid, db=db, current_user=gestor)

            # Paga em lote; a própria função preserva segregação e ajustes.
            batch = await pagar_comissoes_em_lote(
                CommissionBatchIn(
                    withdrawal_ids=[wid],
                    payment_method="pix",
                    paid_at=datetime.now(timezone.utc),
                    payment_reference="TESTE-ROLLBACK",
                ),
                db=db,
                cu=gestor,
            )
            assert Decimal(str(batch["total_pago"])) > 0

            # Ajuste depois do pagamento não reescreve a retirada já paga.
            ajuste = await registrar_ajuste_comissao(
                db,
                allocation_id=alloc["allocation_id"],
                valor_advogado=Decimal("25.00"),
                valor_escritorio=Decimal("-25.00"),
                motivo="ajuste pós-pagamento de teste",
                user=gestor,
            )
            assert ajuste["saldo_pendente"] == Decimal("25.00")

            # Fechamento futuro sem movimento cria snapshot e bloqueio persistente.
            fechamento = await fechar_competencia_financeira(
                FinanceCloseIn(competencia="2099-12"),
                db=db,
                cu=gestor,
            )
            assert fechamento["competencia"] == "2099-12"
            with pytest.raises(HTTPException):
                await exigir_competencia_aberta(
                    db,
                    "2099-12",
                    "Reescrever lançamento",
                )

            # Confirma que o fechamento existe dentro da transação de teste.
            count = (
                await db.execute(
                    text(
                        "SELECT COUNT(*) FROM finance_month_closings "
                        "WHERE competencia='2099-12'"
                    )
                )
            ).scalar()
            assert int(count or 0) == 1
        finally:
            await db.close()
            await outer.rollback()
