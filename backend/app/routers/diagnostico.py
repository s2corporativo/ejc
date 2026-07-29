# ── app/routers/diagnostico.py ───────────────────────────────────────────────
# Central Eletrônica de Diagnóstico — expõe o estado de saúde agregado de todos
# os subsistemas (banco, migrations, IA, integrações, RAG, scheduler, disco…).
#
#   GET /diagnostico/central     — SOCIO+ (require_roles), rate limit 10/min.
#   GET /diagnostico/integridade — SOCIO+ (require_roles), rate limit 5/min.
#
# Observação: NÃO há /diagnostico/health-publico aqui — o app já expõe
# GET /api/health (liveness público) e GET /api/health/ready (readiness). Criar
# outro endpoint público seria duplicação.
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

logger = logging.getLogger("ejc.diagnostico")

router = APIRouter(prefix="/diagnostico", tags=["Central de Diagnóstico"])

# socio+ = socio, admin, superadmin (hierarquia ROLE_LEVEL).
_SOCIO_MAIS = require_roles(["socio"])


def _exigir_diagnostico_habilitado() -> None:
    """Falha fechada para todos os diagnósticos administrativos."""
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
    """Diagnóstico completo: estado de saúde acionável de todos os subsistemas.

    Retorna `status_geral`, `resumo` (contagens por status) e a lista de
    `subsistemas`, cada um com {nome, status, detalhe, acao_sugerida,
    latencia_ms}. Restrito a SOCIO+; limitado a 10 requisições/min.
    """
    _exigir_diagnostico_habilitado()
    return await diagnostico_service.diagnostico_completo(db)


@router.get(
    "/integridade",
    dependencies=[Depends(rate_limit("diagnostico_integridade", 5))],
)
async def integridade_diagnostico(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_SOCIO_MAIS),
):
    """Verifica vínculos e falsos positivos sem alterar qualquer registro.

    O relatório contém somente UUIDs técnicos, contagens, severidade e ação
    recomendada. Não retorna nomes, CPF/CNPJ, número de processo ou conteúdo de
    documentos. Restrito a SOCIO+ e protegido pela mesma feature flag da Central.
    """
    _exigir_diagnostico_habilitado()
    return await integridade_service.diagnosticar_integridade(db)
