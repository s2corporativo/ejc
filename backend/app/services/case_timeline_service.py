"""Orquestra a linha do tempo única do caso sem persistência paralela."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.case_timeline_attendances import attendance_events
from app.services.case_timeline_legal_docs import legal_document_events
from app.services.case_timeline_sources_core import (
    deadline_events,
    document_events,
    movement_events,
    process_events,
)
from app.services.case_timeline_tasks import task_events

_SourceLoader = Callable[
    [AsyncSession, str, int], Awaitable[tuple[list[dict[str, Any]], bool]]
]

_SOURCES: tuple[tuple[str, _SourceLoader], ...] = (
    ("case_movimentos", movement_events),
    ("processes", process_events),
    ("documents", document_events),
    ("deadlines", deadline_events),
    ("tasks", task_events),
    ("atendimentos", attendance_events),
    ("legal_docs", legal_document_events),
)


async def timeline(
    db: AsyncSession,
    case_id: str,
    *,
    page: int = 1,
    per_page: int = 50,
    source_limit: int = 500,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    saturated_sources: list[str] = []

    # AsyncSession não é usada concorrentemente; a ordem sequencial preserva a
    # segurança transacional do SQLAlchemy async.
    for source_name, loader in _SOURCES:
        source_events, saturated = await loader(db, case_id, source_limit)
        events.extend(source_events)
        if saturated:
            saturated_sources.append(source_name)

    events.sort(key=lambda item: item["_sort_at"], reverse=True)
    for item in events:
        item.pop("_sort_at", None)

    start = (page - 1) * per_page
    end = start + per_page
    truncated = bool(saturated_sources)
    return {
        "case_id": case_id,
        "page": page,
        "per_page": per_page,
        "total_loaded": len(events),
        "truncated": truncated,
        "saturated_sources": sorted(saturated_sources),
        "has_more": end < len(events) or truncated,
        "items": events[start:end],
    }
