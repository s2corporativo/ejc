"""
precedentes.py — Busca de precedentes em fontes públicas (STJ, STF, DataJud/CNJ).

Expõe o crawler (app.services.crawler_precedentes) por API autenticada. Como faz
fetch externo, o endpoint tem rate limit. Nenhum resultado é inventado: cada
fonte devolve status "success" / "erro" / "indisponivel" com carimbo de origem.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.core.rate_limit import limiter
from app.core.security import get_current_user
from app.models.user import User
from app.services import crawler_precedentes as cp

router = APIRouter(prefix="/precedentes", tags=["Precedentes"])

_FONTES_VALIDAS = {"stj", "stf", "datajud"}


class BuscaReq(BaseModel):
    termo: str = Field("", max_length=500, description="Termo livre (ementa/tema)")
    fontes: List[str] = Field(
        default_factory=lambda: ["stj", "stf"],
        description="Subconjunto de: stj, stf, datajud",
    )
    numero_cnj: Optional[str] = Field(
        None, max_length=30, description="Número CNJ do processo (para DataJud)"
    )


@router.post("/buscar")
@limiter.limit("20/minute")
async def buscar(
    body: BuscaReq,
    request: Request,
    cu: User = Depends(get_current_user),
):
    """Consolida precedentes das fontes pedidas (fetch externo — rate limited)."""
    fontes = [f for f in body.fontes if f in _FONTES_VALIDAS] or ["stj"]
    return await cp.buscar_precedentes(
        termo=body.termo, fontes=fontes, numero_cnj=body.numero_cnj
    )
