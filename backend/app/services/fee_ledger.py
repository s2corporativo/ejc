"""Ledger canônico de honorários.

A fonte de verdade de recebimentos é exclusivamente fee_payments.
Estornos reduzem o total efetivo do honorário via fee_estornos.
Não há fallback para quitação armazenada apenas em fees.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fee import Fee, FeeEstorno, FeePayment


LEDGER_CTES = """
pagamentos_reais AS (
    SELECT fp.fee_id,
           GREATEST(
               COALESCE(SUM(fp.valor), 0)
               - COALESCE((
                   SELECT SUM(fe.valor)
                   FROM fee_estornos fe
                   WHERE fe.fee_id = fp.fee_id
               ), 0),
               0
           ) AS total_pago,
           COUNT(*) AS qtd_pagamentos
    FROM fee_payments fp
    JOIN fees f ON f.id = fp.fee_id
    WHERE f.deleted_at IS NULL
    GROUP BY fp.fee_id
),
pagamentos_efetivos AS (
    SELECT
        f.id AS fee_id,
        COALESCE(pr.total_pago, 0) AS total_pago
    FROM fees f
    LEFT JOIN pagamentos_reais pr ON pr.fee_id = f.id
    WHERE f.deleted_at IS NULL
),
recebimentos_efetivos AS (
    SELECT
        fp.fee_id,
        fp.valor,
        fp.data_pagamento
    FROM fee_payments fp
    JOIN fees f ON f.id = fp.fee_id
    WHERE f.deleted_at IS NULL
)
"""


async def total_pago_efetivo(db: AsyncSession, fee: Fee) -> tuple[Decimal, bool]:
    """Retorna o total do subledger menos estornos; a origem legada é sempre False."""
    total, _qtd = (
        await db.execute(
            select(
                func.coalesce(func.sum(FeePayment.valor), 0),
                func.count(FeePayment.id),
            ).where(FeePayment.fee_id == fee.id)
        )
    ).one()
    estornos = (
        await db.execute(
            select(func.coalesce(func.sum(FeeEstorno.valor), 0)).where(
                FeeEstorno.fee_id == fee.id
            )
        )
    ).scalar()
    efetivo = Decimal(str(total or 0)) - Decimal(str(estornos or 0))
    if efetivo < 0:
        efetivo = Decimal("0")
    return efetivo, False
