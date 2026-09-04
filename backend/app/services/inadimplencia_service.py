"""
services/inadimplencia_service.py
Verifica honorários vencidos e cria/atualiza alertas escalonados:
  leve (15d) → medio (30d) → critico (60d) → cobranca_formal (90d)

`amount_due` sempre representa SALDO ainda devido, apurado a partir de
fee_payments. Alertas são resolvidos automaticamente quando o saldo zera,
quando a cobrança é cancelada ou removida.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)


def _nivel(days: int) -> str:
    if days >= 90:
        return "cobranca_formal"
    if days >= 60:
        return "critico"
    if days >= 30:
        return "medio"
    return "leve"


async def varrer_inadimplencia(db: AsyncSession) -> dict:
    """Recalcula inadimplência monetária pelo saldo efetivamente em aberto."""
    now = datetime.now(timezone.utc)

    # Primeiro reconcilia alertas que deixaram de representar dívida atual.
    # A ação é automática/derivada e não altera o ledger financeiro.
    await db.execute(text("""
        WITH pagamentos AS (
            SELECT fee_id, COALESCE(SUM(valor), 0) AS total_pago
            FROM fee_payments
            GROUP BY fee_id
        )
        UPDATE inadimplencia_alerts a
        SET resolved = TRUE,
            resolved_at = COALESCE(a.resolved_at, NOW()),
            action_taken = COALESCE(a.action_taken, 'reconciliado_pagamentos'),
            updated_at = NOW()
        FROM fees f
        LEFT JOIN pagamentos p ON p.fee_id = f.id
        WHERE a.fee_id = f.id
          AND a.resolved = FALSE
          AND (
              f.deleted_at IS NOT NULL
              OR CAST(f.status AS text) IN ('pago', 'cancelado')
              OR (f.valor IS NOT NULL
                  AND GREATEST(f.valor - COALESCE(p.total_pago, 0), 0) <= 0)
          )
    """))
    await db.commit()

    r = await db.execute(text("""
        WITH pagamentos AS (
            SELECT fee_id, COALESCE(SUM(valor), 0) AS total_pago
            FROM fee_payments
            GROUP BY fee_id
        )
        SELECT f.id AS fee_id, f.case_id, f.client_id,
               GREATEST(f.valor - COALESCE(p.total_pago, 0), 0) AS amount_due,
               f.data_vencimento AS due_date
        FROM fees f
        LEFT JOIN pagamentos p ON p.fee_id = f.id
        WHERE CAST(f.status AS text) IN ('pendente','atrasado')
          AND f.data_vencimento < NOW()
          AND f.deleted_at IS NULL
          AND f.valor IS NOT NULL
          AND GREATEST(f.valor - COALESCE(p.total_pago, 0), 0) > 0
        ORDER BY f.data_vencimento ASC
        LIMIT 500
    """))
    fees = r.fetchall()

    inserted = 0
    updated = 0
    falhas = 0

    for fee in fees:
        try:
            days = (now.date() - fee.due_date).days if fee.due_date else 0
            nivel = _nivel(days)

            existing = await db.execute(text("""
                SELECT id, alert_level FROM inadimplencia_alerts
                WHERE fee_id = :fee_id AND resolved = FALSE
                LIMIT 1
            """), {"fee_id": fee.fee_id})
            row = existing.fetchone()

            amount_due = float(fee.amount_due or 0)
            if row:
                await db.execute(text("""
                    UPDATE inadimplencia_alerts
                    SET alert_level = :nivel, days_overdue = :days,
                        amount_due = :amount, updated_at = NOW()
                    WHERE id = :id
                """), {
                    "nivel": nivel,
                    "days": days,
                    "amount": amount_due,
                    "id": row.id,
                })
                acao = "updated"
            else:
                await db.execute(text("""
                    INSERT INTO inadimplencia_alerts
                        (id, fee_id, case_id, client_id, days_overdue, amount_due, alert_level)
                    VALUES
                        (gen_random_uuid()::text, :fee_id, :case_id, :client_id,
                         :days, :amount, :nivel)
                """), {
                    "fee_id": fee.fee_id,
                    "case_id": fee.case_id,
                    "client_id": fee.client_id,
                    "days": days,
                    "amount": amount_due,
                    "nivel": nivel,
                })
                acao = "inserted"

            if days >= 15:
                await db.execute(text("""
                    UPDATE fees SET status='atrasado', updated_at=NOW()
                    WHERE id = :id AND status='pendente'
                """), {"id": fee.fee_id})

            await db.commit()
            if acao == "inserted":
                inserted += 1
            else:
                updated += 1
        except Exception as e:
            await db.rollback()
            falhas += 1
            logger.error(
                f"[Inadimplencia] varrer falhou p/ fee {fee.fee_id}: {e}"
            )
            continue

    return {
        "varridas": len(fees),
        "inseridas": inserted,
        "atualizadas": updated,
        "falhas": falhas,
    }


async def listar_alertas(
    db: AsyncSession,
    resolved: bool = False,
    nivel: str | None = None,
    limit: int = 50,
) -> list[dict]:
    filters = ["a.resolved = :resolved"]
    params: dict = {"resolved": resolved, "limit": limit}
    if nivel:
        filters.append("a.alert_level = :nivel")
        params["nivel"] = nivel
    where = " AND ".join(filters)

    r = await db.execute(text(f"""
        SELECT a.id, a.fee_id, a.case_id, a.client_id,
               a.days_overdue, a.amount_due, a.alert_level,
               a.action_taken, a.resolved, a.created_at,
               cl.nome AS client_nome,
               c.numero_interno AS case_number
        FROM inadimplencia_alerts a
        LEFT JOIN clients cl ON cl.id = a.client_id
        LEFT JOIN cases c ON c.id = a.case_id
        WHERE {where}
        ORDER BY a.days_overdue DESC
        LIMIT :limit
    """), params)
    return [dict(row._mapping) for row in r.fetchall()]


async def resolver_alerta(db: AsyncSession, alert_id: str, action: str) -> dict:
    result = await db.execute(text("""
        UPDATE inadimplencia_alerts
        SET resolved = TRUE, resolved_at = NOW(),
            action_taken = :action, updated_at = NOW()
        WHERE id = :id AND resolved = FALSE
        RETURNING id
    """), {"id": alert_id, "action": action})
    row = result.first()
    if row is None:
        await db.rollback()
        return {"resolved": False, "alert_id": alert_id, "reason": "not_found_or_already_resolved"}
    await db.commit()
    return {"resolved": True, "alert_id": alert_id}
