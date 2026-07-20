"""Eventos de movimentação, processo, documento e prazo para a timeline."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import CaseMovimento
from app.models.deadline import Deadline
from app.models.document import Document
from app.models.process import Process
from app.services.case_activity_utils import bounded, enum_value, event


async def movement_events(
    db: AsyncSession, case_id: str, limit: int
) -> tuple[list[dict[str, Any]], bool]:
    raw = (
        await db.execute(
            select(CaseMovimento)
            .where(CaseMovimento.case_id == case_id)
            .order_by(
                CaseMovimento.data_evento.desc().nullslast(),
                CaseMovimento.created_at.desc(),
            )
            .limit(limit + 1)
        )
    ).scalars().all()
    rows, saturated = bounded(raw, limit)
    return (
        [
            event(
                event_id=row.id,
                kind="movement",
                title=f"Movimentação: {enum_value(row.tipo)}",
                description=row.descricao,
                occurred_at=row.data_evento or row.created_at,
                source="case_movimentos",
                metadata={"resumo_ia": row.resumo_ia},
            )
            for row in rows
        ],
        saturated,
    )


async def process_events(
    db: AsyncSession, case_id: str, limit: int
) -> tuple[list[dict[str, Any]], bool]:
    raw = (
        await db.execute(
            select(Process)
            .where(Process.case_id == case_id, Process.deleted_at.is_(None))
            .order_by(Process.updated_at.desc().nullslast(), Process.created_at.desc())
            .limit(limit + 1)
        )
    ).scalars().all()
    rows, saturated = bounded(raw, limit)
    return (
        [
            event(
                event_id=row.id,
                kind="process",
                title=("Processo principal" if row.is_principal else "Processo vinculado"),
                description=row.numero_cnj or "Processo sem numeração informada",
                occurred_at=row.updated_at or row.created_at,
                status=enum_value(row.status),
                source="processes",
                metadata={
                    "numero_cnj": row.numero_cnj,
                    "tipo": enum_value(row.tipo),
                    "tribunal": row.tribunal,
                    "is_principal": bool(row.is_principal),
                    "processo_principal_id": row.processo_principal_id,
                },
            )
            for row in rows
        ],
        saturated,
    )


async def document_events(
    db: AsyncSession, case_id: str, limit: int
) -> tuple[list[dict[str, Any]], bool]:
    raw = (
        await db.execute(
            select(Document)
            .where(Document.case_id == case_id, Document.deleted_at.is_(None))
            .order_by(Document.updated_at.desc().nullslast(), Document.created_at.desc())
            .limit(limit + 1)
        )
    ).scalars().all()
    rows, saturated = bounded(raw, limit)
    return (
        [
            event(
                event_id=row.id,
                kind="document",
                title=row.titulo,
                description=row.filename,
                occurred_at=row.updated_at or row.created_at,
                source="documents",
                metadata={
                    "tipo": enum_value(row.tipo),
                    "confidencialidade": enum_value(row.confidencialidade),
                    "drive_link": row.drive_link,
                },
            )
            for row in rows
        ],
        saturated,
    )


async def deadline_events(
    db: AsyncSession, case_id: str, limit: int
) -> tuple[list[dict[str, Any]], bool]:
    raw = (
        await db.execute(
            select(Deadline)
            .where(Deadline.case_id == case_id, Deadline.deleted_at.is_(None))
            .order_by(Deadline.data_prazo.desc())
            .limit(limit + 1)
        )
    ).scalars().all()
    rows, saturated = bounded(raw, limit)
    return (
        [
            event(
                event_id=row.id,
                kind="deadline",
                title=row.titulo,
                description=row.descricao,
                occurred_at=row.data_prazo,
                status=enum_value(row.status),
                source="deadlines",
                metadata={
                    "tipo": enum_value(row.tipo),
                    "prioridade": enum_value(row.prioridade),
                    "confirmado": bool(row.confirmado),
                    "origem": row.origem,
                    "responsavel_id": row.responsavel_id,
                    "event_time_type": "due_date",
                },
            )
            for row in rows
        ],
        saturated,
    )
