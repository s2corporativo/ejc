"""Funções puras compartilhadas pela timeline e saúde operacional do caso."""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any, Sequence, TypeVar

_T = TypeVar("_T")


def enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def as_utc_datetime(value: datetime | date | None) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)
    return datetime.min.replace(tzinfo=timezone.utc)


def bounded(rows: Sequence[_T], limit: int) -> tuple[list[_T], bool]:
    """Consome resultado obtido com `LIMIT limit + 1`."""
    saturated = len(rows) > limit
    return list(rows[:limit]), saturated


def event(
    *,
    event_id: str,
    kind: str,
    title: str,
    occurred_at: datetime | date | None,
    description: str | None = None,
    status: str | None = None,
    source: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dt = as_utc_datetime(occurred_at)
    return {
        "id": f"{source}:{event_id}",
        "entity_id": event_id,
        "kind": kind,
        "title": title,
        "description": description,
        "status": status,
        "source": source,
        "occurred_at": dt.isoformat(),
        "metadata": metadata or {},
        "_sort_at": dt,
    }
