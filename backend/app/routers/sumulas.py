# ── app/routers/sumulas.py ────────────────────────────────────────────────────
# Banco de Súmulas — ingestão e busca de súmulas STF/STJ/TST no banco de teses.
# POST /sumulas/ingerir-seed  — admin/superadmin only
# GET  /sumulas/buscar        — busca full-text na tabela teses (tipo=jurisprudencia)
# POST /casos/verificar-conflito  — verifica conflito de interesses (qualquer auth)
# ─────────────────────────────────────────────────────────────────────────────
from typing import Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.user import User

router = APIRouter(tags=["Súmulas e Conflito"])


# ─── Schemas ─────────────────────────────────────────────────────────────────
class ConflitoRequest(BaseModel):
    parte_contraria_nome: Optional[str] = None
    parte_contraria_doc:  Optional[str] = None
    case_id:              Optional[str] = None


# ─── Súmulas: ingestão seed ──────────────────────────────────────────────────
@router.post("/sumulas/ingerir-seed")
async def ingerir_seed(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Ingere dataset de súmulas STF/STJ/TST na tabela teses. Apenas admin/superadmin."""
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["admin"]:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Apenas admin pode ingerir súmulas.")
    from app.services.sumulas_ingestion import ingerir_sumulas_seed
    return await ingerir_sumulas_seed(db)


# ─── Súmulas: busca ──────────────────────────────────────────────────────────
@router.get("/sumulas/buscar")
async def buscar_sumulas(
    q:        str           = Query("", description="Texto livre"),
    area:     Optional[str] = Query(None),
    tribunal: Optional[str] = Query(None, description="STF | STJ | TST"),
    limit:    int           = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User         = Depends(get_current_user),
):
    """Busca súmulas/jurisprudência no banco de teses por texto, área ou tribunal."""
    conditions = ["tipo = 'jurisprudencia'", "deleted_at IS NULL"]
    params: dict = {"limit": limit}

    if q:
        conditions.append("(titulo ILIKE :q OR descricao ILIKE :q OR tags ILIKE :q)")
        params["q"] = f"%{q}%"
    if area:
        conditions.append("area_juridica = :area")
        params["area"] = area
    if tribunal:
        conditions.append("tribunal = :tribunal")
        params["tribunal"] = tribunal

    where = " AND ".join(conditions)
    rows = (await db.execute(text(f"""
        SELECT id, titulo, descricao, area_juridica, tribunal, tags, vezes_usada
        FROM teses
        WHERE {where}
        ORDER BY vezes_usada DESC, titulo
        LIMIT :limit
    """), params)).mappings().all()

    return {
        "total": len(rows),
        "sumulas": [dict(r) for r in rows],
        "filtros": {"q": q, "area": area, "tribunal": tribunal},
    }


# ─── Conflito de Interesses ───────────────────────────────────────────────────
@router.post("/casos/verificar-conflito")
async def verificar_conflito(
    req: ConflitoRequest,
    db:  AsyncSession = Depends(get_db),
    cu:  User         = Depends(get_current_user),
):
    """
    Verifica conflito de interesses antes de abrir um caso.
    OAB EOAB art. 34-35; Código de Ética arts. 15-18.
    """
    from app.services.conflito_interesses import verificar_conflito as _verificar
    return await _verificar(
        db=db,
        parte_contraria_nome=req.parte_contraria_nome,
        parte_contraria_doc=req.parte_contraria_doc,
        user_id=cu.id,
        case_id=req.case_id,
    )
