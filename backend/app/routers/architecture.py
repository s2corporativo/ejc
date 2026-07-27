"""Governança arquitetural e manifesto de rotas do EJC."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.route_registry import build_route_manifest
from app.core.security import require_admin, require_roles

router = APIRouter(prefix="/architecture", tags=["Arquitetura"])
_GESTORES = ["superadmin", "admin", "socio"]


@router.get("/routes")
async def route_manifest(request: Request, _=Depends(require_roles(_GESTORES))):
    """Lista endpoints efetivamente montados e colisões exatas de método+caminho."""
    return build_route_manifest(request.app)


@router.get("/uso-rotas")
async def uso_de_rotas(
    desde: str | None = None,
    _=Depends(require_admin),
):
    """Agregado de USO das rotas candidatas à remoção (legadas, duplicatas e alias).

    Insumo da decisão da Onda 5: rota com `total = 0` numa janela de 30-60 dias
    sem restart pode ser removida. `desde` filtra por hora ISO (ex.:
    2026-07-01T00:00:00+00:00). Sem PII — ver services/route_usage.py.
    """
    from app.services import route_usage

    return route_usage.agregado(desde)


@router.get("/contracts")
async def domain_contracts(_=Depends(require_roles(_GESTORES))):
    """Expõe o vocabulário canônico sem revelar dados de negócio."""
    from app.core.domain_contracts import (
        CaseLifecycleStatus,
        DocumentLifecycleStatus,
        FinancialLifecycleStatus,
        TaskLifecycleStatus,
    )

    return {
        "case_status": [item.value for item in CaseLifecycleStatus],
        "task_status": [item.value for item in TaskLifecycleStatus],
        "document_status": [item.value for item in DocumentLifecycleStatus],
        "financial_status": [item.value for item in FinancialLifecycleStatus],
        "api_canonical_prefix": "/api/v1",
        "api_legacy_prefix": "/api",
    }
