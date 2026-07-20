"""Eventos de peças jurídicas para a timeline consolidada."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.legal_doc import LegalDoc
from app.services.case_activity_utils import bounded, enum_value, event


async def legal_document_events(
    db: AsyncSession, case_id: str, limit: int
) -> tuple[list[dict[str, Any]], bool]:
    raw = (
        await db.execute(
            select(LegalDoc)
            .where(LegalDoc.case_id == case_id, LegalDoc.deleted_at.is_(None))
            .order_by(LegalDoc.updated_at.desc().nullslast(), LegalDoc.created_at.desc())
            .limit(limit + 1)
        )
    ).scalars().all()
    rows, saturated = bounded(raw, limit)
    return (
        [
            event(
                event_id=row.id,
                kind="legal_document",
                title=row.titulo,
                description=f"Versão {row.versao}",
                occurred_at=(
                    row.protocolado_em
                    or row.revisado_em
                    or row.updated_at
                    or row.created_at
                ),
                status=enum_value(row.status),
                source="legal_docs",
                metadata={
                    "tipo_peca": enum_value(row.tipo_peca),
                    "codigo_peca": row.codigo_peca,
                    "ai_generated": bool(row.ai_generated),
                    "human_reviewed": bool(row.human_reviewed),
                    "numero_protocolo": row.numero_protocolo,
                },
            )
            for row in rows
        ],
        saturated,
    )
