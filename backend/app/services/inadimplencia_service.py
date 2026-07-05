"""
services/inadimplencia_service.py
Verifica honorários vencidos e cria/atualiza alertas escalonados:
  leve (15d) → medio (30d) → critico (60d) → cobranca_formal (90d)
"""
from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


def _nivel(days: int) -> str:
    if days >= 90:
        return "cobranca_formal"
    if days >= 60:
        return "critico"
    if days >= 30:
        return "medio"
    return "leve"


async def varrer_inadimplencia(db: AsyncSession) -> dict:
    """Varre fees vencidas e insere/atualiza inadimplencia_alerts. Chamado pelo scheduler."""
    now = datetime.now(timezone.utc)

    # Fees vencidas e não pagas
    # NB: o schema real usa f.valor / f.data_vencimento (não amount/due_date).
    r = await db.execute(text("""
        SELECT f.id AS fee_id, f.case_id, f.client_id,
               f.valor AS amount_due, f.data_vencimento AS due_date
        FROM fees f
        WHERE f.status IN ('pendente','atrasado')
          AND f.data_vencimento < NOW()
          AND f.deleted_at IS NULL
        ORDER BY f.data_vencimento ASC
        LIMIT 500
    """))
    fees = r.fetchall()

    inserted = 0
    updated = 0

    for fee in fees:
        days = (now.date() - fee.due_date).days if fee.due_date else 0
        nivel = _nivel(days)

        # Verificar se já existe alerta não resolvido
        existing = await db.execute(text("""
            SELECT id, alert_level FROM inadimplencia_alerts
            WHERE fee_id = :fee_id AND resolved = FALSE
            LIMIT 1
        """), {"fee_id": fee.fee_id})
        row = existing.fetchone()

        if row:
            # SEMPRE refresca days_overdue/amount_due (não só na troca de nível):
            # antes, um alerta que permanecia na mesma faixa (ex.: "medio",
            # 30-59d) congelava days_overdue no valor do dia em que entrou na
            # faixa — o painel de cobrança (ordenado por days_overdue) mostrava
            # dias em atraso desatualizados até o nível mudar.
            await db.execute(text("""
                UPDATE inadimplencia_alerts
                SET alert_level = :nivel, days_overdue = :days,
                    amount_due = :amount, updated_at = NOW()
                WHERE id = :id
            """), {"nivel": nivel, "days": days,
                   "amount": float(fee.amount_due or 0), "id": row.id})
            updated += 1
        else:
            await db.execute(text("""
                INSERT INTO inadimplencia_alerts
                    (id, fee_id, case_id, client_id, days_overdue, amount_due, alert_level)
                VALUES
                    (gen_random_uuid()::text, :fee_id, :case_id, :client_id,
                     :days, :amount, :nivel)
            """), {
                "fee_id":    fee.fee_id,
                "case_id":   fee.case_id,
                "client_id": fee.client_id,
                "days":      days,
                "amount":    float(fee.amount_due or 0),
                "nivel":     nivel,
            })
            inserted += 1

        # Atualizar status da fee
        if days >= 15:
            await db.execute(text("""
                UPDATE fees SET status='atrasado', updated_at=NOW()
                WHERE id = :id AND status='pendente'
            """), {"id": fee.fee_id})

    await db.commit()
    return {"varridas": len(fees), "inseridas": inserted, "atualizadas": updated}


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
    await db.execute(text("""
        UPDATE inadimplencia_alerts
        SET resolved = TRUE, resolved_at = NOW(),
            action_taken = :action, updated_at = NOW()
        WHERE id = :id
    """), {"id": alert_id, "action": action})
    await db.commit()
    return {"resolved": True, "alert_id": alert_id}
