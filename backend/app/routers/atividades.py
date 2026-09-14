"""Fonte única de atividades — lê a VIEW vw_atividades (prazos+tarefas+suspensões+agenda+intimações).
   Substitui a agregação no frontend por uma chamada só.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ownership import is_gestao
from app.models.user import User
from app.schemas.activity_alert import ActivityAlertStateUpdate
from app.services.activity_alert_service import listar_alertas_inteligentes, marcar_estado_alerta

router = APIRouter(prefix="/atividades", tags=["Central de Atividades"])


@router.get("")
async def listar_atividades(
    apenas_pendentes: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    where = "WHERE 1=1"
    params: dict = {}
    if apenas_pendentes:
        where += " AND COALESCE(v.status,'') NOT IN ('concluido','concluida','tratada','cancelado')"
    # Visibilidade: gestão vê tudo; equipe só as atividades das quais é responsável
    # OU vinculadas a casos em que atua (responsável/auxiliar). Evita vazar prazos/
    # tarefas/intimações de casos alheios na central de atividades.
    if not is_gestao(cu):
        where += """ AND (v.responsavel_id = :uid OR EXISTS (
            SELECT 1 FROM cases cc WHERE cc.id = v.case_id
              AND (cc.advogado_responsavel_id = :uid OR cc.advogado_auxiliar_id = :uid)
        ))"""
        params["uid"] = cu.id
    # (v.data::date - CURRENT_DATE) força diferença em DIAS inteiros mesmo se a
    # coluna for TIMESTAMP (senão vem interval → int() estoura 500).
    # SQL literal com bind params; a regra marca todo text(), sem olhar
    # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
    # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
    rows = (await db.execute(text(f"""
        SELECT v.id, v.tipo, v.titulo, v.descricao, v.data, v.status,
               v.case_id, v.responsavel_id, v.prioridade, v.subtipo,
               c.titulo AS caso_titulo,
               (v.data::date - CURRENT_DATE) AS dias_restantes
        FROM vw_atividades v
        LEFT JOIN cases c ON c.id = v.case_id
        {where}
        ORDER BY v.data ASC NULLS LAST
    """), params)).mappings().all()

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

    def _dias(d):
        # Robusto: aceita int (date - date) ou timedelta (fallback de driver).
        if d is None:
            return None
        if hasattr(d, "days"):
            return d.days
        return int(d)

    data = []
    for r in rows:
        di = _dias(r["dias_restantes"])
        data.append({
            "id": r["id"], "tipo": r["tipo"], "titulo": r["titulo"],
            "descricao": r["descricao"], "date": str(r["data"]) if r["data"] else None,
            "status": r["status"], "case_id": r["case_id"], "caso_titulo": r["caso_titulo"],
            "responsavel_id": r["responsavel_id"], "prioridade": r["prioridade"],
            "subtipo": r["subtipo"],
            "dias_restantes": di, "urgencia": urg(di),
        })
    return {"data": data}


@router.get("/alertas-inteligentes")
async def alertas_inteligentes(
    limit_per_type: int = Query(5, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    return await listar_alertas_inteligentes(
        db, cu, limit_per_type=limit_per_type
    )


@router.patch("/alertas/{source_type}/{source_id}")
async def atualizar_estado_alerta(
    source_type: str,
    source_id: str,
    payload: ActivityAlertStateUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    return await marcar_estado_alerta(
        db, cu, source_type, source_id, payload.estado
    )
