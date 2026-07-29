"""Governança arquitetural e manifesto de rotas do EJC."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request

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
    desde: datetime | None = Query(
        None,
        description=("Filtra a partir desta data/hora (ISO 8601). Aceita data pura "
                     "(2026-06-01) ou data-hora (2026-06-01T00:00:00+00:00). "
                     "Valor inválido → 422, nunca silencioso."),
    ),
    _=Depends(require_admin),
):
    """Agregado de USO das rotas candidatas à remoção (legadas, duplicatas e alias).

    Insumo da decisão da Onda 5: rota com `total = 0` numa janela de 30-60 dias
    pode ser removida. `desde` é VALIDADO pelo contrato (Pydantic `datetime`):
    string malformada devolve 422 em vez de descartar o histórico e devolver
    zeros — que seria lido como "sem uso" (P1-1). Se o histórico persistido não
    puder ser lido, a resposta traz `historico_indisponivel: true` e OMITE
    `sem_uso_no_periodo`. Sem identificadores diretos — ver services/route_usage.py.
    """
    from app.services import route_usage

    return await route_usage.agregado_persistido(desde)


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
