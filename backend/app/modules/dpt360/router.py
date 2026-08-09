from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_roles
from app.models.user import User
from app.modules.dpt360.dashboard_service import build_dashboard
from app.modules.dpt360.schemas import DptDashboardResponse

router = APIRouter(prefix="/dpt360", tags=["DPT Empresarial 360"])


@router.get("/dashboard", response_model=DptDashboardResponse)
async def dashboard(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["advogado"])),
) -> DptDashboardResponse:
    """Cockpit empresarial read-only, sempre respeitando o escopo do usuário."""
    return await build_dashboard(db, cu)
