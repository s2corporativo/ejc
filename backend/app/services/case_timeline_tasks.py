"""Eventos de tarefas para a timeline consolidada."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.services.case_activity_utils import bounded, enum_value, event


async def task_events(
    db: AsyncSession, case_id: str, limit: int
) -> tuple[list[dict[str, Any]], bool]:
    raw = (
        await db.execute(
            select(Task)
            .where(Task.case_id == case_id, Task.deleted_at.is_(None))
            .order_by(Task.updated_at.desc().nullslast(), Task.created_at.desc())
            .limit(limit + 1)
        )
    ).scalars().all()
    rows, saturated = bounded(raw, limit)
    return (
        [
            event(
                event_id=row.id,
                kind="task",
                title=row.titulo,
                description=row.descricao,
                occurred_at=row.concluida_em or row.updated_at or row.created_at,
                status=enum_value(row.status),
                source="tasks",
                metadata={
                    "prioridade": row.prioridade,
                    "data_limite": row.data_limite.isoformat() if row.data_limite else None,
                    "responsavel_id": row.responsavel_id,
                },
            )
            for row in rows
        ],
        saturated,
    )
