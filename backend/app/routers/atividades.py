"""Fonte única de atividades — lê a VIEW vw_atividades (prazos+tarefas+suspensões+agenda+intimações).
   Substitui a agregação no frontend por uma chamada só.
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(prefix="/atividades", tags=["Central de Atividades"])

_VIEW_SOURCE_SQL = """
    SELECT v.id, v.tipo, v.titulo, v.descricao, v.data, v.status,
           v.case_id, v.responsavel_id
    FROM vw_atividades v
"""

_FALLBACK_SOURCE_SQL = """
    SELECT d.id, 'prazo' AS tipo, d.titulo, d.descricao,
           d.data_prazo AS data, d.status::text AS status,
           d.case_id, d.responsavel_id
    FROM deadlines d
    WHERE d.deleted_at IS NULL

    UNION ALL

    SELECT t.id, 'tarefa' AS tipo, t.titulo, t.descricao,
           t.data_limite AS data, t.status::text AS status,
           t.case_id, t.responsavel_id
    FROM tasks t
    WHERE t.deleted_at IS NULL

    UNION ALL

    SELECT e.id, e.tipo, e.titulo, e.descricao,
           e.data_evento AS data,
           CASE WHEN e.concluido THEN 'concluida' ELSE 'pendente' END AS status,
           e.case_id, e.responsavel_id
    FROM agenda_eventos e
    WHERE e.deleted_at IS NULL

    UNION ALL

    SELECT s.id, 'suspensao' AS tipo,
           ('Suspensão de prazo - ' || s.tribunal) AS titulo,
           COALESCE(s.ato_normativo || ' - ', '') || s.motivo AS descricao,
           s.data_inicio AS data,
           CASE WHEN s.data_fim < CURRENT_DATE THEN 'concluida' ELSE 'pendente' END AS status,
           NULL AS case_id, s.created_by AS responsavel_id
    FROM suspensoes_tribunal s
    WHERE s.deleted_at IS NULL

    UNION ALL

    SELECT i.id, 'intimacao' AS tipo,
           COALESCE(i.tipo_comunicacao, 'Intimação DJEN') AS titulo,
           i.texto_resumo AS descricao,
           i.data_disponibilizacao AS data,
           CASE WHEN i.processada THEN 'tratada' ELSE 'pendente' END AS status,
           i.case_id, i.advogado_id AS responsavel_id
    FROM djen_comunicacoes i
"""


def _query_atividades(source_sql: str, apenas_pendentes: bool) -> str:
    where = "WHERE 1=1"
    if apenas_pendentes:
        where += " AND COALESCE(v.status,'') NOT IN ('concluido','concluida','tratada','cancelado')"
    return f"""
        SELECT v.id, v.tipo, v.titulo, v.descricao, v.data, v.status,
               v.case_id, v.responsavel_id,
               c.titulo AS caso_titulo,
               (v.data - CURRENT_DATE) AS dias_restantes
        FROM ({source_sql}) v
        LEFT JOIN cases c ON c.id = v.case_id
        {where}
        ORDER BY v.data ASC NULLS LAST
    """


@router.get("")
async def listar_atividades(
    apenas_pendentes: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    try:
        rows = (await db.execute(
            text(_query_atividades(_VIEW_SOURCE_SQL, apenas_pendentes))
        )).mappings().all()
    except SQLAlchemyError:
        await db.rollback()
        rows = (await db.execute(
            text(_query_atividades(_FALLBACK_SOURCE_SQL, apenas_pendentes))
        )).mappings().all()

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
