"""
Router de precedentes multi-fonte.

Montado dinamicamente em /api/jurisprudencia-externa/precedentes/* para evitar
alterar o router grande de jurisprudência externa nesta etapa.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.rate_limit import rate_limit
from app.core.security import ROLE_LEVEL, get_current_user
from app.models.user import User
from app.services.crawler_precedentes import buscar_precedentes

router = APIRouter(prefix="/precedentes", tags=["Precedentes"])


class BuscaPrecedentesRequest(BaseModel):
    termo: str = Field(..., min_length=3, max_length=500)
    fontes: list[str] = Field(default_factory=lambda: ["lexml", "tjmg"])
    numero_cnj: Optional[str] = Field(None, max_length=30)
    pagina: int = Field(1, ge=1)
    por_pagina: int = Field(10, ge=1, le=30)


def _is_staff(u: User) -> bool:
    return ROLE_LEVEL.get(u.role.value, 0) >= ROLE_LEVEL["estagiario"]


@router.post("/buscar", dependencies=[Depends(rate_limit("precedentes_multifonte", 10))])
async def buscar_precedentes_endpoint(
    req: BuscaPrecedentesRequest,
    cu: User = Depends(get_current_user),
):
    """Busca precedentes em múltiplas fontes com status honesto por fonte."""
    if not _is_staff(cu):
        raise HTTPException(status_code=403, detail="Sem permissão")
    return await buscar_precedentes(
        termo=req.termo,
        fontes=req.fontes,
        numero_cnj=req.numero_cnj,
        pagina=req.pagina,
        por_pagina=req.por_pagina,
    )
