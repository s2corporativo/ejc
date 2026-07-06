from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_roles
from app.models.user import User
from app.services.autofix_scanner import gerar_diagnostico_basico

router = APIRouter(prefix="/autofix", tags=["Diagnostico do Sistema"])

_gestores = require_roles(["superadmin", "admin", "socio"])


@router.get("/diagnostico-basico")
async def diagnostico_basico(
    request: Request,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_gestores),
):
    return await gerar_diagnostico_basico(db, request.app)
