# ── app/routers/diagnostico.py ───────────────────────────────────────────────
# Central Eletrônica de Diagnóstico — saúde técnica + jurídico-operacional.
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import require_roles
from app.models.user import User
from app.services import diagnostico_service, integridade_service
from app.services.diagnostico_juridico_operacional import diagnosticar as diagnosticar_juridico

logger = logging.getLogger("ejc.diagnostico")
router = APIRouter(prefix="/diagnostico", tags=["Central de Diagnóstico"])
_SOCIO_MAIS = require_roles(["socio"])


def _exigir_diagnostico_habilitado() -> None:
    if not get_settings().DIAGNOSTICO_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Central de Diagnóstico desabilitada (DIAGNOSTICO_ENABLED=false).",
        )


@router.get(
    "/central",
    dependencies=[Depends(rate_limit("diagnostico_central", 10))],
)
async def central_diagnostico(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_SOCIO_MAIS),
):
    """Saúde técnica agregada + fila jurídico-operacional, somente leitura."""
    _exigir_diagnostico_habilitado()
    payload = await diagnostico_service.diagnostico_completo(db)
    juridico = await diagnosticar_juridico(db)
    payload["subsistemas"].append(juridico)
    status, resumo = diagnostico_service.agregar(payload["subsistemas"])
    payload["status_geral"] = status
    payload["resumo"] = resumo
    payload["aviso"] = (
        "Diagnóstico somente-leitura. Além da saúde técnica, inclui contagens "
        "jurídico-operacionais sem PII (prazos, DJEN, NFS-e e contratos)."
    )
    return payload


@router.get(
    "/integridade",
    dependencies=[Depends(rate_limit("diagnostico_integridade", 5))],
)
async def integridade_diagnostico(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_SOCIO_MAIS),
):
    _exigir_diagnostico_habilitado()
    return await integridade_service.diagnosticar_integridade(db)
