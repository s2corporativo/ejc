# ── app/routers/movimentos.py ─────────────────────────────────────────────────
# Movimentações/andamentos recentes de TODOS os casos (para o dashboard).
from __future__ import annotations
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ownership import is_gestao
from app.models.user import User

router = APIRouter(prefix="/movimentos", tags=["Movimentações"])


@router.get("/recentes")
async def recentes(
    limit: int = Query(15, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    # Feed de movimentos: gestão vê todos os casos; equipe só os casos em que atua
    # (responsável/auxiliar) + casos órfãos (sem dono, mesma salvaguarda anti-lockout
    # de verificar_acesso_caso). Assim o painel não vaza andamentos de casos alheios.
    params: dict = {"lim": limit}
    escopo = ""
    if not is_gestao(cu):
        escopo = """
            AND (c.advogado_responsavel_id = :uid
                 OR c.advogado_auxiliar_id = :uid
                 OR (c.advogado_responsavel_id IS NULL
                     AND c.advogado_auxiliar_id IS NULL))
        """
        params["uid"] = cu.id
    res = await db.execute(
        # SQL literal com bind params; a regra marca todo text(), sem olhar
        # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        text(f"""
            SELECT m.id, m.case_id, m.tipo, m.descricao,
                   COALESCE(m.data_evento, m.created_at) AS quando,
                   m.created_at AS created_at,
                   m.data_evento AS data_evento,
                   c.titulo AS case_titulo, c.numero_interno
            FROM case_movimentos m
            JOIN cases c ON c.id = m.case_id
            WHERE c.deleted_at IS NULL{escopo}
            ORDER BY COALESCE(m.data_evento, m.created_at) DESC
            LIMIT :lim
        """),
        params,
    )
    return [dict(r) for r in res.mappings().all()]
