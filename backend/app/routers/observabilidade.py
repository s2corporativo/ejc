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
    # Encaminha ao Sentry quando configurado (mesmo backend já integrado).
    if get_settings().SENTRY_DSN:
        try:
            import sentry_sdk

            with sentry_sdk.push_scope() as scope:
                scope.set_tag("origin", "frontend")
                scope.set_user({"id": cu.id})
                scope.set_extra("url", err.url)
                scope.set_extra("stack", err.stack)
                scope.set_extra("component_stack", err.component_stack)
                scope.set_extra("user_agent", err.user_agent)
                sentry_sdk.capture_message(
                    f"[frontend] {err.message[:200]}", level="error"
                )
        except Exception:  # noqa: BLE001 — telemetria nunca deve quebrar
            logger.warning("[frontend-error] falha ao encaminhar ao Sentry", exc_info=True)
    return None
