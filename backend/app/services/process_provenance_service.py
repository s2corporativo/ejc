"""Proveniência append-only de metadados processuais."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.process_integrity import ProcessDataProvenance

SOURCE_TYPES = {
    "usuario", "documento", "datajud", "djen", "tribunal",
    "importacao", "entrada_unica", "sistema",
}


async def registrar_proveniencia(
    db: AsyncSession,
    *,
    process_id: str,
    campos: dict[str, Any],
    source_type: str,
    source_ref: str | None = None,
    source_date: datetime | None = None,
    confidence: str | None = None,
    confirmed_by: str | None = None,
) -> list[ProcessDataProvenance]:
    if source_type not in SOURCE_TYPES:
        raise ValueError("Fonte de proveniência inválida")
    agora = datetime.now(timezone.utc)
    rows: list[ProcessDataProvenance] = []
    for field_name, value in campos.items():
        if value is None:
            continue
        row = ProcessDataProvenance(
            id=str(uuid4()),
            process_id=process_id,
            field_name=str(field_name)[:64],
            source_type=source_type,
            source_ref=(str(source_ref)[:255] if source_ref else None),
            source_date=source_date,
            value_snapshot={"value": jsonable_encoder(value, custom_encoder={Decimal: str})},
            confidence=(str(confidence)[:20] if confidence else None),
            confirmed_by=confirmed_by,
            confirmed_at=agora if confirmed_by else None,
        )
        db.add(row)
        rows.append(row)
    if rows:
        await db.flush()
    return rows


async def listar_proveniencia(
    db: AsyncSession, process_id: str
) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(ProcessDataProvenance)
            .where(ProcessDataProvenance.process_id == process_id)
            .order_by(
                ProcessDataProvenance.field_name,
                ProcessDataProvenance.captured_at.desc(),
            )
        )
    ).scalars().all()
    return [
        {
            "id": row.id,
            "field_name": row.field_name,
            "source_type": row.source_type,
            "source_ref": row.source_ref,
            "source_date": row.source_date,
            "captured_at": row.captured_at,
            "value_snapshot": row.value_snapshot,
            "confidence": row.confidence,
            "confirmed_by": row.confirmed_by,
            "confirmed_at": row.confirmed_at,
        }
        for row in rows
    ]
