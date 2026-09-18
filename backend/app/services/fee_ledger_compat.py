"""Compatibilidade de leitura do ledger de honorários.

Antes da adoção de ``fee_payments`` como subledger canônico, o EJC permitia
registrar quitação diretamente em ``fees.status/data_pagamento``. Esses dados
históricos não podem desaparecer dos relatórios quando o novo ledger entra em
vigor.

Regra de transição, deliberadamente NÃO duplicante:
1. se existe ao menos um ``fee_payments`` para o fee, somente o subledger vale;
2. se não existe nenhum pagamento e o fee legado está ``pago``, possui
   ``data_pagamento`` e ``valor`` monetário, o valor do fee é lido como
   recebimento legado;
3. honorários soft-deleted não participam de saldo nem caixa;
4. nenhum registro sintético é gravado automaticamente. A normalização física
   deverá ser feita em migration/backfill controlado quando a cadeia Alembic
   estiver disponível.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fee import Fee, FeeEstorno, FeePayment, FeeStatus


LEDGER_COMPAT_CTES = """
pagamentos_reais AS (
    SELECT fp.fee_id,
           GREATEST(COALESCE(SUM(fp.valor), 0) - COALESCE((
               SELECT SUM(fe.valor) FROM fee_estornos fe
               WHERE fe.fee_id = fp.fee_id
           ), 0), 0) AS total_pago,
           COUNT(*) AS qtd_pagamentos
    FROM fee_payments fp
    JOIN fees f ON f.id = fp.fee_id
    WHERE f.deleted_at IS NULL
    GROUP BY fp.fee_id
),
pagamentos_efetivos AS (
    SELECT
        f.id AS fee_id,
        CASE
            WHEN COALESCE(pr.qtd_pagamentos, 0) > 0 THEN pr.total_pago
            WHEN CAST(f.status AS text) = 'pago'
                 AND f.data_pagamento IS NOT NULL
                 AND f.valor IS NOT NULL
            THEN f.valor
            ELSE 0
        END AS total_pago,
        CASE
            WHEN COALESCE(pr.qtd_pagamentos, 0) = 0
                 AND CAST(f.status AS text) = 'pago'
                 AND f.data_pagamento IS NOT NULL
                 AND f.valor IS NOT NULL
            THEN TRUE ELSE FALSE
        END AS legado_sem_subledger
    FROM fees f
    LEFT JOIN pagamentos_reais pr ON pr.fee_id = f.id
    WHERE f.deleted_at IS NULL
),
recebimentos_efetivos AS (
    SELECT fp.fee_id, fp.valor, fp.data_pagamento, FALSE AS legado_sem_subledger
    FROM fee_payments fp
    JOIN fees f ON f.id = fp.fee_id
    WHERE f.deleted_at IS NULL
    UNION ALL
    SELECT f.id AS fee_id, f.valor, f.data_pagamento, TRUE AS legado_sem_subledger
    FROM fees f
    WHERE f.deleted_at IS NULL
      AND CAST(f.status AS text) = 'pago'
      AND f.data_pagamento IS NOT NULL
      AND f.valor IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM fee_payments fp WHERE fp.fee_id = f.id
      )
)
"""


async def total_pago_efetivo(
    db: AsyncSession,
    fee: Fee,
) -> tuple[Decimal, bool]:
    """Retorna total efetivo e se a origem é o fallback legado.

    O total EFETIVO é ``Σ pagamentos − Σ estornos`` do subledger (piso em
    zero). Estorno é lançamento próprio de ``fee_estornos`` — o caixa real
    muda quando um pagamento é revertido, e todo consumidor deste total
    (saldo, quitação, resumo) precisa enxergar o mesmo número.
    """
    total, qtd = (
        await db.execute(
            select(
                func.coalesce(func.sum(FeePayment.valor), 0),
                func.count(FeePayment.id),
            ).where(FeePayment.fee_id == fee.id)
        )
    ).one()
    if int(qtd or 0) > 0:
        estornos = (
            await db.execute(
                select(
                    func.coalesce(func.sum(FeeEstorno.valor), 0)
                ).where(FeeEstorno.fee_id == fee.id)
            )
        ).scalar()
        efetivo = Decimal(str(total or 0)) - Decimal(str(estornos or 0))
        if efetivo < 0:
            efetivo = Decimal("0")
        return efetivo, False

    if (
        fee.status == FeeStatus.pago
        and fee.data_pagamento is not None
        and fee.valor is not None
    ):
        return Decimal(str(fee.valor)), True

    return Decimal("0"), False
