"""Fonte única de atividades — lê a VIEW vw_atividades (prazos+tarefas+suspensões+agenda+intimações).
   Substitui a agregação no frontend por uma chamada só.
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(prefix="/atividades", tags=["Central de Atividades"])


@router.get("")
async def listar_atividades(
    apenas_pendentes: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    where = "WHERE 1=1"
    if apenas_pendentes:
        where += " AND COALESCE(v.status,'') NOT IN ('concluido','concluida','tratada','cancelado')"
    rows = (await db.execute(text(f"""
        SELECT v.id, v.tipo, v.titulo, v.descricao, v.data, v.status,
               v.case_id, v.responsavel_id,
               c.titulo AS caso_titulo,
               (v.data - CURRENT_DATE) AS dias_restantes
        FROM vw_atividades v
        LEFT JOIN cases c ON c.id = v.case_id
        {where}
        ORDER BY v.data ASC NULLS LAST
    """))).mappings().all()

    def urg(d):
        if d is None:
            return "normal"
        if d < 0:
            return "vencido"
        if d <= 3:
            return "critico"
        if d <= 7:
            return "atencao"
        return "normal"

    data = []
    for r in rows:
        d = r["dias_restantes"]
        di = int(d) if d is not None else None
        data.append({
            "id": r["id"], "tipo": r["tipo"], "titulo": r["titulo"],
            "descricao": r["descricao"], "date": str(r["data"]) if r["data"] else None,
            "status": r["status"], "case_id": r["case_id"], "caso_titulo": r["caso_titulo"],
            "dias_restantes": di, "urgencia": urg(di),
        })
    return {"data": data}
