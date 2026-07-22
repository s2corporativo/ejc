"""Resumo de saúde dos casos ativos para o Dashboard."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.portfolio_health_service import portfolio_health

# Incluído dentro de dashboard.router, prefixo final /dashboard/operational-health.
router = APIRouter(tags=["Dashboard — Saúde Operacional"])
_ALLOWED = {
    "superadmin",
    "admin",
    "socio",
    "advogado",
    "advogado_auxiliar",
    "estagiario",
}
_OFFICE_SCOPE = {"superadmin", "admin", "socio"}


@router.get("/operational-health")
async def dashboard_operational_health(
    stale_days: int = Query(30, ge=7, le=365),
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    role = cu.role.value
    if role not in _ALLOWED:
        raise HTTPException(403, "Perfil sem acesso à saúde operacional da carteira")
    return await portfolio_health(
        db,
        user_id=cu.id,
        scope_all=role in _OFFICE_SCOPE,
        stale_days=stale_days,
        limit=limit,
    )
