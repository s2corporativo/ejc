from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_roles
from app.models.user import User
from app.modules.dpt360.company_service import get_company_profile
from app.modules.dpt360.dashboard_service import build_dashboard
from app.modules.dpt360.intelligence_service import run_dpt_action
from app.modules.dpt360.schemas import (
    DptActionRequest,
    DptActionResponse,
    DptCompanyProfile,
    DptDashboardResponse,
)

router = APIRouter(prefix="/dpt360", tags=["DPT Empresarial 360"])


@router.get("/dashboard", response_model=DptDashboardResponse)
async def dashboard(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["advogado"])),
) -> DptDashboardResponse:
    """Cockpit empresarial read-only, sempre respeitando o escopo do usuário."""
    return await build_dashboard(db, cu)


@router.get("/companies/{client_id}", response_model=DptCompanyProfile)
async def company_profile(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["advogado"])),
) -> DptCompanyProfile:
    """Perfil Jurídico Vivo derivado somente de registros canônicos visíveis."""
    profile = await get_company_profile(db, cu, client_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    return profile


@router.post("/actions", response_model=DptActionResponse)
async def run_action(
    payload: DptActionRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["advogado"])),
) -> DptActionResponse:
    """Motor Jurídico DPT: Conselho, pré-flight e diagnóstico via núcleo único."""
    result = await run_dpt_action(db, cu, payload)
    if result is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    return result
