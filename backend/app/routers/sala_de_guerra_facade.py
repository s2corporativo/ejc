"""Capacidades avançadas dentro do workspace canônico da Sala de Guerra.

Este router é incluído como subrouter de `sala_de_guerra.router`; as rotas finais
ficam sob `/cases/{case_id}/sala-de-guerra/*`. Os endpoints históricos
`/sala-de-guerra-v3/*` continuam ativos durante a migração.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(tags=["Sala de Guerra — capacidades avançadas"])


class SimulacaoAdversarialRequest(BaseModel):
    peticao: str = Field(min_length=20, max_length=200_000)


class VisualLawRequest(BaseModel):
    eventos: list[dict[str, Any]] | None = None


@router.post(
    "/simular-contestacao",
    dependencies=[Depends(rate_limit("war-room-simular-caso", 10))],
)
async def simular_contestacao_do_caso(
    case_id: str,
    body: SimulacaoAdversarialRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Simula a linha adversarial já vinculada e auditada no caso atual."""
    from app.routers.sala_de_guerra_v3 import simular_war_room

    return await simular_war_room(
        payload={"peticao": body.peticao, "case_id": case_id},
        db=db,
        cu=cu,
    )


@router.post(
    "/visual-law",
    dependencies=[Depends(rate_limit("visual-law-pdf-caso", 10))],
)
async def gerar_visual_law_do_caso(
    case_id: str,
    body: VisualLawRequest | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Gera a cronologia Visual Law a partir do contexto do caso."""
    from app.routers.sala_de_guerra_v3 import gerar_visual_law

    result = await gerar_visual_law(
        case_id=case_id,
        payload=body.model_dump(exclude_none=True) if body else {},
        db=db,
        cu=cu,
    )
    return {
        **result,
        "download_url": f"/cases/{case_id}/sala-de-guerra/visual-law/download",
    }


@router.get("/visual-law/download")
async def baixar_visual_law_do_caso(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Baixa a versão mais recente da cronologia Visual Law do caso."""
    from app.routers.sala_de_guerra_v3 import download_visual_law

    return await download_visual_law(case_id=case_id, db=db, cu=cu)
