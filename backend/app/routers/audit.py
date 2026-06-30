# ── app/routers/audit.py ─────────────────────────────────────────────────────
# Consulta de audit logs — somente leitura, somente admin/socio.
from __future__ import annotations
from typing import Optional
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_roles
from app.models.user import User
from app.models.audit_log import AuditLog

router = APIRouter(prefix="/audit", tags=["Auditoria"])


@router.get("/")
async def listar(
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    acao: Optional[str] = None,
    entidade: Optional[str] = None,
    user_id: Optional[str] = None,
    data_de: Optional[date] = None,
    data_ate: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio"])),
):
    q = select(AuditLog)
    if acao:
        q = q.where(AuditLog.acao == acao)
    if entidade:
        q = q.where(AuditLog.entidade == entidade)
    if user_id:
        q = q.where(AuditLog.user_id == user_id)
    if data_de:
        q = q.where(sqlfunc.date(AuditLog.created_at) >= data_de)
    if data_ate:
        q = q.where(sqlfunc.date(AuditLog.created_at) <= data_ate)
    q = q.order_by(AuditLog.created_at.desc())

    total = (await db.execute(
        select(sqlfunc.count()).select_from(q.subquery())
    )).scalar()
    rows = (await db.execute(
        q.offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {
        "data": [
            {"id": l.id, "user_id": l.user_id, "user_role": l.user_role,
             "acao": l.acao, "entidade": l.entidade,
             "registro_id": l.registro_id, "detalhes": l.detalhes,
             "ip": l.ip, "created_at": l.created_at}
            for l in rows
        ],
        "total": total, "page": page, "page_size": page_size,
    }
