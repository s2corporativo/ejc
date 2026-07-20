"""Linha do tempo consolidada e diagnóstico operacional por caso."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.security import get_current_user
from app.models.user import User
from app.services import case_health_service, case_timeline_service

# Incluído dentro de `cases.router`, cujo prefixo é /cases.
router = APIRouter(prefix="/{case_id}", tags=["Casos — Linha do Tempo"])


@router.get("/timeline")
async def case_timeline(
    case_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    source_limit: int = Query(500, ge=50, le=2000),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Eventos dos domínios do caso em ordem cronológica decrescente."""
    await verificar_acesso_caso(db, cu, case_id)
    return await case_timeline_service.timeline(
        db,
        case_id,
        page=page,
        per_page=per_page,
        source_limit=source_limit,
    )


@router.get("/operational-health")
async def case_operational_health(
    case_id: str,
    stale_days: int = Query(30, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Inatividade, prazos, solicitações e pendências de produção."""
    await verificar_acesso_caso(db, cu, case_id)
    result = await case_health_service.operational_health(
        db,
        case_id,
        stale_days=stale_days,
    )
    if not result.get("found"):
        raise HTTPException(404, "Caso não encontrado")
    return result
