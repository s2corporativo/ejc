# ── app/routers/movimentos.py ─────────────────────────────────────────────────
# Movimentações/andamentos recentes de TODOS os casos (para o dashboard).
from __future__ import annotations
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(prefix="/movimentos", tags=["Movimentações"])


@router.get("/recentes")
async def recentes(
    limit: int = Query(15, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    res = await db.execute(
        text("""
            SELECT m.id, m.case_id, m.tipo, m.descricao,
                   COALESCE(m.data_evento, m.created_at) AS quando,
                   c.titulo AS case_titulo, c.numero_interno
            FROM case_movimentos m
            JOIN cases c ON c.id = m.case_id
            WHERE c.deleted_at IS NULL
            ORDER BY COALESCE(m.data_evento, m.created_at) DESC
            LIMIT :lim
        """),
        {"lim": limit},
    )
    return [dict(r) for r in res.mappings().all()]
