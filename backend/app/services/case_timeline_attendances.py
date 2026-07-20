"""Eventos de atendimentos para a timeline consolidada."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.atendimento import Atendimento
from app.services.case_activity_utils import bounded, enum_value, event


async def attendance_events(
    db: AsyncSession, case_id: str, limit: int
) -> tuple[list[dict[str, Any]], bool]:
    raw = (
        await db.execute(
            select(Atendimento)
            .where(Atendimento.case_id == case_id)
            .order_by(Atendimento.data_atendimento.desc())
            .limit(limit + 1)
        )
    ).scalars().all()
    rows, saturated = bounded(raw, limit)
    return (
        [
            event(
                event_id=row.id,
                kind="attendance",
                title=f"Atendimento: {enum_value(row.tipo)}",
                description=row.resumo,
                occurred_at=row.data_atendimento,
                status=("atendida" if row.solicitacao_atendida else "pendente"),
                source="atendimentos",
                metadata={
                    "solicitacao": row.solicitacao,
                    "proximo_passo": row.proximo_passo,
                    "prazo_retorno": (
                        row.solicitacao_prazo.isoformat()
                        if row.solicitacao_prazo
                        else None
                    ),
                    "contato_status": row.contato_status,
                },
            )
            for row in rows
        ],
        saturated,
    )
