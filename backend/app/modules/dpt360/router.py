from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import require_roles
from app.models.user import User
from app.modules.dpt360.company_service import get_company_profile
from app.modules.dpt360.dashboard_service import build_dashboard
from app.modules.dpt360.diagnostic_service import build_diagnostic_readiness
from app.modules.dpt360.intake_schemas import DptInboundOpportunity, DptInboundOpportunityOut
from app.modules.dpt360.intake_service import (
    create_inbound_opportunity,
    list_inbound_opportunities,
)
from app.modules.dpt360.intelligence_service import run_dpt_action
from app.modules.dpt360.radar_service import build_today_radar
from app.modules.dpt360.report_service import build_executive_report
from app.modules.dpt360.schemas import (
    DptActionRequest,
    DptActionResponse,
    DptCompanyProfile,
    DptDashboardResponse,
    DptDiagnosticKind,
    DptDiagnosticReadiness,
    DptOpportunityQueueItem,
)

router = APIRouter(prefix="/dpt360", tags=["DPT Empresarial 360"])
DPT_ROLES = ["superadmin", "admin", "socio", "advogado"]


@router.get("/dashboard", response_model=DptDashboardResponse)
async def dashboard(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(DPT_ROLES)),
) -> DptDashboardResponse:
    result = await build_dashboard(db, cu)
    radar = await build_today_radar(db, cu, hours=24)
    result.metrics.mudancas_juridicas_hoje = int(radar["total_publicacoes"])
    result.metrics.empresas_potencialmente_impactadas = int(
        radar["empresas_potencialmente_impactadas"]
    )
    result.radar_por_area = {
        str(area): int(total) for area, total in (radar.get("por_area") or {}).items()
    }
    result.notes.append(
        "Radar do dashboard usa publicações coletadas nas últimas 24h; vigência permanece a confirmar até o gate canônico de vigência do RAG ser reconciliado."
    )
    return result


@router.get("/companies/{client_id}", response_model=DptCompanyProfile)
async def company_profile(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(DPT_ROLES)),
) -> DptCompanyProfile:
    profile = await get_company_profile(db, cu, client_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    return profile


@router.get(
    "/diagnostics/readiness/{client_id}", response_model=DptDiagnosticReadiness
)
async def diagnostic_readiness(
    client_id: str,
    kind: DptDiagnosticKind = Query(default="completo"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(DPT_ROLES)),
) -> DptDiagnosticReadiness:
    result = await build_diagnostic_readiness(db, cu, client_id, kind)
    if result is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    return result


@router.get("/radar/today")
async def radar_today(
    hours: int = Query(default=24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(DPT_ROLES)),
):
    return await build_today_radar(db, cu, hours=hours)


@router.get("/reports/executive/{client_id}")
async def executive_report(
    client_id: str,
    days: int = Query(default=30, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(DPT_ROLES)),
):
    report = await build_executive_report(db, cu, client_id, days=days)
    if report is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    return report


@router.get(
    "/intake/opportunities",
    response_model=list[DptOpportunityQueueItem],
)
async def intake_opportunity_queue(
    limit: int = Query(default=100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(DPT_ROLES)),
) -> list[DptOpportunityQueueItem]:
    """Fila interna, minimizada e autenticada; nunca expõe mensagem/contato."""
    return await list_inbound_opportunities(db, cu, limit=limit)


@router.post(
    "/intake/opportunities",
    response_model=DptInboundOpportunityOut,
    dependencies=[Depends(rate_limit("dpt360-intake-opportunity", 10))],
)
async def intake_opportunity(
    payload: DptInboundOpportunity,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(DPT_ROLES)),
) -> DptInboundOpportunityOut:
    """Entrada autenticada interna. Não é endpoint público do site."""
    return await create_inbound_opportunity(db, cu, payload)


@router.post(
    "/actions",
    response_model=DptActionResponse,
    dependencies=[Depends(rate_limit("dpt360-ai-actions", 10))],
)
async def run_action(
    payload: DptActionRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(DPT_ROLES)),
) -> DptActionResponse:
    result = await run_dpt_action(db, cu, payload)
    if result is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    return result
