# ── app/routers/diario_oficial.py ─────────────────────────────────────────────
# Monitor de Diário Oficial — gerência de keywords e visualização de alertas.
# A captura efetiva ocorre no scheduler (job diário 06h00).
from __future__ import annotations
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.user import User
from app.models.case import Case
from app.models.diario_oficial import DiarioOficialKeyword, DiarioOficialAlerta

router = APIRouter(prefix="/diario-oficial", tags=["Diário Oficial"])


class KeywordIn(BaseModel):
    keyword: str = Field(min_length=2, max_length=200)
    fonte:   str = "dou"   # dou|doe_mg|dom
    case_id: Optional[str] = None


def _pode_editar(u: User) -> bool:
    return ROLE_LEVEL.get(u.role.value, 0) >= ROLE_LEVEL["advogado"]


def _filtrar_por_ownership(q, coluna_case_id, user: User):
    """#10(b): antes as listagens do Diário retornavam TODOS os itens sem filtro.
    Mesmo limiar de cases._filtro_visibilidade: gestão (socio+) vê tudo; a equipe
    vê os itens SEM caso (office-wide — keyword/alerta geral do escritório) OU os
    atrelados a casos em que é responsável/auxiliar. Preserva a visibilidade
    compartilhada dos itens office-wide e a total para a gestão."""
    if ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["socio"]:
        return q
    casos_visiveis = select(Case.id).where(or_(
        Case.advogado_responsavel_id == user.id,
        Case.advogado_auxiliar_id == user.id,
    ))
    return q.where(or_(coluna_case_id.is_(None), coluna_case_id.in_(casos_visiveis)))


# ── Keywords ──────────────────────────────────────────────────────────────────

@router.get("/keywords")
async def listar_keywords(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    q = _filtrar_por_ownership(
        select(DiarioOficialKeyword), DiarioOficialKeyword.case_id, cu
    ).order_by(DiarioOficialKeyword.keyword)
    kws = (await db.execute(q)).scalars().all()
    return [{"id": k.id, "keyword": k.keyword, "fonte": k.fonte,
             "ativo": k.ativo, "case_id": k.case_id} for k in kws]


@router.post("/keywords", status_code=201)
async def criar_keyword(
    req: KeywordIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    k = DiarioOficialKeyword(id=str(uuid4()), created_by=cu.id, **req.model_dump())
    db.add(k)
    await db.commit()
    return {"id": k.id, "keyword": k.keyword, "fonte": k.fonte}


@router.delete("/keywords/{keyword_id}", status_code=204)
async def remover_keyword(
    keyword_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    k = (await db.execute(
        select(DiarioOficialKeyword).where(DiarioOficialKeyword.id == keyword_id)
    )).scalar_one_or_none()
    if not k:
        raise HTTPException(404)
    await db.delete(k)
    await db.commit()


# ── Alertas ───────────────────────────────────────────────────────────────────

@router.get("/alertas")
async def listar_alertas(
    lido:    Optional[bool] = Query(None),
    fonte:   Optional[str]  = Query(None),
    case_id: Optional[str]  = Query(None),
    page:    int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db:      AsyncSession = Depends(get_db),
    cu:      User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    q = _filtrar_por_ownership(select(DiarioOficialAlerta), DiarioOficialAlerta.case_id, cu)
    if lido is not None:
        q = q.where(DiarioOficialAlerta.lido.is_(lido))
    if fonte:
        q = q.where(DiarioOficialAlerta.fonte == fonte)
    if case_id:
        q = q.where(DiarioOficialAlerta.case_id == case_id)
    q = q.order_by(DiarioOficialAlerta.data_publicacao.desc())
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    items = (await db.execute(q.offset((page-1)*per_page).limit(per_page))).scalars().all()
    return {
        "total": total, "page": page, "per_page": per_page,
        "items": [
            {
                "id": a.id, "fonte": a.fonte, "edicao": a.edicao,
                "data_publicacao": a.data_publicacao.isoformat() if a.data_publicacao else None,
                "secao": a.secao, "titulo": a.titulo, "resumo": a.resumo,
                "link": a.link, "keyword_match": a.keyword_match,
                "lido": a.lido, "case_id": a.case_id,
            }
            for a in items
        ],
    }


@router.patch("/alertas/{alerta_id}/marcar-lido")
async def marcar_lido(
    alerta_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    a = (await db.execute(
        select(DiarioOficialAlerta).where(DiarioOficialAlerta.id == alerta_id)
    )).scalar_one_or_none()
    if not a:
        raise HTTPException(404)
    a.lido = True
    await db.commit()
    return {"id": alerta_id, "lido": True}


@router.get("/alertas/nao-lidos/count")
async def contar_nao_lidos(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    q = _filtrar_por_ownership(
        select(func.count(DiarioOficialAlerta.id)), DiarioOficialAlerta.case_id, cu
    ).where(DiarioOficialAlerta.lido.is_(False))
    total = (await db.execute(q)).scalar() or 0
    return {"nao_lidos": total}
