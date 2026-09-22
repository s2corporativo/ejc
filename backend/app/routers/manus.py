from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, requer_equipe_juridica
from app.models.user import User
from app.services.manus_deep_reasoning import consultar_raciocinio, iniciar_raciocinio

router = APIRouter(prefix="/manus", tags=["IA — Manus"])


class ManusDeepRequest(BaseModel):
    texto: str = Field(min_length=30, max_length=16000)
    area: str | None = Field(default=None, max_length=100)
    case_id: str | None = Field(default=None, max_length=64)


@router.post(
    "/deep-reasoning",
    status_code=202,
    dependencies=[Depends(rate_limit("manus-deep-create", 6))],
)
async def criar(
    body: ManusDeepRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    requer_equipe_juridica(user, "Raciocínio Profundo é restrito à equipe jurídica.")
    return await iniciar_raciocinio(
        db,
        user=user,
        texto=body.texto,
        area=body.area,
        case_id=body.case_id,
    )


@router.get(
    "/deep-reasoning/{handle}",
    dependencies=[Depends(rate_limit("manus-deep-status", 30))],
)
async def consultar(
    handle: str,
    user: User = Depends(get_current_user),
):
    requer_equipe_juridica(user, "Raciocínio Profundo é restrito à equipe jurídica.")
    return await consultar_raciocinio(user=user, handle=handle)
