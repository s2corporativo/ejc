# ── app/routers/observabilidade.py ───────────────────────────────────────────
# Recebe erros de RENDERIZAÇÃO do frontend (capturados pelo ErrorBoundary) para
# dar visibilidade a crashes de tela SEM depender de auditoria manual de console.
# Loga estruturado.
from __future__ import annotations
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(prefix="/observabilidade", tags=["Observabilidade"])
logger = logging.getLogger("ejc.frontend")


class FrontendError(BaseModel):
    message: str = Field(..., max_length=2000)
    stack: str | None = Field(None, max_length=8000)
    component_stack: str | None = Field(None, max_length=8000)
    url: str | None = Field(None, max_length=500)
    user_agent: str | None = Field(None, max_length=500)


@router.post("/frontend-error", status_code=204)
async def registrar_erro_frontend(
    err: FrontendError,
    cu: User = Depends(get_current_user),
):
    """Registra um crash de renderização do frontend. Autenticado (o
    AuthMiddleware já exige JWT) — cobre os erros de tela dos usuários logados."""
    logger.error(
        "[frontend-error] user=%s url=%s msg=%s",
        cu.id, err.url, err.message[:500],
    )
    return None
