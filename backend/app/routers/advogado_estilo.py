"""Router de aprendizado de estilo do advogado."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import ROLE_LEVEL, get_current_user
from app.models.user import User
from app.services.advogado_style_service import gerar_perfil_estilo

router = APIRouter(prefix="/advogado-estilo", tags=["Aprendizado de Estilo"])


def _pode_usar_estilo(u: User) -> bool:
    return ROLE_LEVEL.get(u.role.value, 0) >= ROLE_LEVEL["estagiario"]


@router.get("/me")
async def meu_estilo(
    limite: int = Query(12, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Gera perfil de estilo do usuário autenticado, sem persistir dados."""
    if not _pode_usar_estilo(cu):
        raise HTTPException(status_code=403, detail="Sem permissão")
    return await gerar_perfil_estilo(db, cu.id, limite=limite)
