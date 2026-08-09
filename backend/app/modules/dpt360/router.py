from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_roles
from app.models.user import User
from app.modules.dpt360.company_service import get_company_profile
from app.modules.dpt360.dashboard_service import build_dashboard
from app.modules.dpt360.diagnostic_service import build_diagnostic_readiness
from app.modules.dpt360.intelligence_service import run_dpt_action
from app.modules.dpt360.radar_service import build_today_radar
from app.modules.dpt360.schemas import (
    DptActionRequest,
    DptActionResponse,
    DptCompanyProfile,
    DptDashboardResponse,
    DptDiagnosticReadiness,
)

router = APIRouter(prefix="/dpt360", tags=["DPT Empresarial 360"])


@router.get("/dashboard", response_model=DptDashboardResponse)
async def dashboard(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["advogado"])),
) -> DptDashboardResponse:
    return await build_dashboard(db, cu)


@router.get("/companies/{client_id}", response_model=DptCompanyProfile)
async def company_profile(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["advogado"])),
) -> DptCompanyProfile:
    profile = await get_company_profile(db, cu, client_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    return profile


@router.get("/diagnostics/readiness/{client_id}", response_model=DptDiagnosticReadiness)
async def diagnostic_readiness(
    client_id: str,
    kind: str = Query(default="completo", max_length=40),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["advogado"])),
) -> DptDiagnosticReadiness:
    result = await build_diagnostic_readiness(db, cu, client_id, kind)
    if result is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    return DptDiagnosticReadiness.model_validate(result)


@router.get("/radar/today")
async def radar_today(
    hours: int = Query(default=24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["advogado"])),
):
    """Digest regulatório DPT: leitura de dados já coletados pelo scheduler."""
    return await build_today_radar(db, cu, hours=hours)


@router.post("/actions", response_model=DptActionResponse)
async def run_action(
    payload: DptActionRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["advogado"])),
) -> DptActionResponse:
    result = await run_dpt_action(db, cu, payload)
    if result is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    return result
