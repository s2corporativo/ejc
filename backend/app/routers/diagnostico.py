# ── app/routers/diagnostico.py ───────────────────────────────────────────────
# Central Eletrônica de Diagnóstico — expõe o estado de saúde agregado de todos
# os subsistemas (banco, migrations, IA, integrações, RAG, scheduler, disco…).
#
#   GET /diagnostico/central — SOCIO+ (require_roles), rate limit 10/min.
#
# Observação: NÃO há /diagnostico/health-publico aqui — o app já expõe
# GET /api/health (liveness público) e GET /api/health/ready (readiness). Criar
# outro endpoint público seria duplicação.
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import require_roles
from app.models.user import User
from app.services import diagnostico_service
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("ejc.diagnostico")

router = APIRouter(prefix="/diagnostico", tags=["Central de Diagnóstico"])

# socio+ = socio, admin, superadmin (hierarquia ROLE_LEVEL).
_SOCIO_MAIS = require_roles(["socio"])


@router.get(
    "/central",
    dependencies=[Depends(rate_limit("diagnostico_central", 10))],
)
async def central_diagnostico(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_SOCIO_MAIS),
):
    """Diagnóstico completo: estado de saúde acionável de todos os subsistemas.

    Retorna `status_geral`, `resumo` (contagens por status) e a lista de
    `subsistemas`, cada um com {nome, status, detalhe, acao_sugerida,
    latencia_ms}. Restrito a SOCIO+; limitado a 10 requisições/min.
    """
    if not get_settings().DIAGNOSTICO_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Central de Diagnóstico desabilitada (DIAGNOSTICO_ENABLED=false).",
        )
    return await diagnostico_service.diagnostico_completo(db)
