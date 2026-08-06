"""Fachada canônica de timeline e saúde operacional dentro de /cases."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.security import get_current_user
from app.models.user import User
from app.services import case_health, case_timeline_service

# Incluído no router canônico de casos, cujo prefixo é /cases.
router = APIRouter(prefix="/{case_id}", tags=["Casos — Timeline e Saúde"])


@router.get("/timeline")
async def timeline_caso(
    case_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    source_limit: int = Query(500, ge=50, le=2000),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Agrega eventos já persistidos, sem duplicar ou migrar dados."""
    await verificar_acesso_caso(db, cu, case_id)
    return await case_timeline_service.timeline(
        db,
        cu,
        case_id,
        page=page,
        per_page=per_page,
        source_limit=source_limit,
    )


@router.get("/operational-health")
async def saude_operacional_caso(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Expõe no workspace o score determinístico já usado em Analytics."""
    case = await verificar_acesso_caso(db, cu, case_id)
    return await case_health.calcular_score_caso(db, case)
