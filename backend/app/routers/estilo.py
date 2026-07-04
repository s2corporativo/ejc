"""
Router: Aprendizado de Estilo do advogado.

O sistema destila o estilo de redação de cada advogado a partir de peças
aprovadas e o reutiliza (opt-in) na geração de novas peças.

Ownership ESTRITO: todo endpoint opera sobre o advogado autenticado (cu.id).
Não existe parâmetro de user_id — um advogado jamais acessa o estilo de outro.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.models.user import User
from app.services.estilo_service import (
    definir_ativo,
    destilar_amostra,
    limpar_estilo,
    obter_estilo,
)

router = APIRouter(prefix="/estilo", tags=["Aprendizado de Estilo"])


class AmostraRequest(BaseModel):
    texto: str = Field(..., min_length=50, max_length=20000,
                       description="Peça aprovada, base para destilar o estilo")
    substituir: bool = Field(
        False,
        description="Descarta o perfil atual e recomeça a partir desta amostra",
    )


class AtivoRequest(BaseModel):
    ativo: bool = Field(..., description="Usar o estilo na geração de peças?")


def _serializar(estilo) -> dict:
    if estilo is None:
        return {
            "perfil_estilo": None,
            "n_amostras": 0,
            "ativo": False,
            "existe": False,
        }
    return {
        "perfil_estilo": estilo.perfil_estilo,
        "n_amostras": estilo.n_amostras,
        "ativo": estilo.ativo,
        "existe": True,
        "created_at": estilo.created_at,
        "updated_at": estilo.updated_at,
    }


@router.post("/amostras", dependencies=[Depends(rate_limit("estilo_amostra", 10))])
async def adicionar_amostra(
    req: AmostraRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Destila/refina o perfil de estilo do advogado logado a partir de uma peça
    aprovada. Sanitiza (LGPD), passa pelo AI Gateway e grava AILog."""
    estilo = await destilar_amostra(db, cu.id, req.texto, substituir=req.substituir)
    return _serializar(estilo)


@router.get("/meu")
async def meu_estilo(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Perfil de estilo do advogado logado (vazio se ainda não houver)."""
    return _serializar(await obter_estilo(db, cu.id))


@router.patch("/meu")
async def alternar_ativo(
    req: AtivoRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Liga/desliga o uso do estilo na geração de peças."""
    return _serializar(await definir_ativo(db, cu.id, req.ativo))


@router.delete("/meu")
async def apagar_estilo(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Limpa o perfil de estilo do advogado logado."""
    removido = await limpar_estilo(db, cu.id)
    return {"removido": removido, **_serializar(None)}
