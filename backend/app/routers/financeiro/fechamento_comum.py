"""Persistência transacional dos snapshots de fechamento financeiro."""
from datetime import datetime
import json
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_INSERTS = {
    "comissoes": text("""INSERT INTO commission_month_closings
        (id,competencia,snapshot_json,closed_by,closed_at,created_at)
        VALUES (:id,:competencia,CAST(:snapshot AS jsonb),:closed_by,:closed_at,NOW())"""),
    "financeiro": text("""INSERT INTO finance_month_closings
        (id,competencia,snapshot_json,closed_by,closed_at,created_at)
        VALUES (:id,:competencia,CAST(:snapshot AS jsonb),:closed_by,:closed_at,NOW())"""),
}


async def persistir_fechamento(
    db: AsyncSession, *, tipo: Literal["comissoes", "financeiro"],
    cid: str, competencia: str, snapshot: dict, closed_by: str, closed_at: datetime,
) -> None:
    await db.execute(_INSERTS[tipo], {
        "id": cid, "competencia": competencia,
        "snapshot": json.dumps(snapshot, default=str, ensure_ascii=False),
        "closed_by": closed_by, "closed_at": closed_at,
    })
