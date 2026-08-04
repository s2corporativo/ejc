# ── app/routers/jurisprudencia_interna.py ────────────────────────────────────
# Repositório Interno de Jurisprudência — CRUD + classificação por IA.
from __future__ import annotations
import logging
from uuid import uuid4
from datetime import datetime, timezone, date as _date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL, EQUIPE_JURIDICA
from app.models.user import User
from app.models.jurisprudencia_interna import JurisprudenciaInterna, JuriResultado
from app.core.rate_limit import rate_limit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jurisprudencias", tags=["Jurisprudência Interna"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class JuriIn(BaseModel):
    titulo:          str = Field(min_length=5, max_length=300)
    ementa:          str = Field(min_length=20)
    fundamentacao:   Optional[str] = None
    tribunal:        Optional[str] = None
    relator:         Optional[str] = None
    numero_acordao:  Optional[str] = None
    data_julgamento: Optional[_date] = None
    fonte:           Optional[str] = "manual"
    link_original:   Optional[str] = None
    area_juridica:   Optional[str] = None
    tags:            Optional[str] = None
    resultado:       Optional[JuriResultado] = None
    favorito:        bool = False


class JuriPatch(BaseModel):
    titulo:          Optional[str] = None
    ementa:          Optional[str] = None
    fundamentacao:   Optional[str] = None
    tribunal:        Optional[str] = None
    relator:         Optional[str] = None
    area_juridica:   Optional[str] = None
    tags:            Optional[str] = None
    resultado:       Optional[JuriResultado] = None
    favorito:        Optional[bool] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_staff(u: User) -> bool:
    # Issue #694: allowlist EXATA — financeiro não acessa o repositório interno
    # de jurisprudência, mesmo com ROLE_LEVEL acima de estagiario.
    return u.role.value in EQUIPE_JURIDICA

def _pode_editar(u: User) -> bool:
    return ROLE_LEVEL.get(u.role.value, 0) >= ROLE_LEVEL["advogado"]

def _out(j: JurisprudenciaInterna) -> dict:
    return {
        "id": j.id, "titulo": j.titulo, "ementa": j.ementa,
        "fundamentacao": j.fundamentacao,
        "tribunal": j.tribunal, "relator": j.relator,
        "numero_acordao": j.numero_acordao,
        "data_julgamento": j.data_julgamento.isoformat() if j.data_julgamento else None,
        "fonte": j.fonte, "link_original": j.link_original,
        "area_juridica": j.area_juridica, "tags": j.tags,
        "resultado": j.resultado.value if j.resultado and hasattr(j.resultado, "value") else j.resultado,
        "favorito": j.favorito, "vezes_citada": j.vezes_citada,
        "created_at": j.created_at.isoformat() if j.created_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def listar_jurisprudencias(
    area:      Optional[str] = Query(None),
    tribunal:  Optional[str] = Query(None),
    resultado: Optional[str] = Query(None),
    favorito:  Optional[bool] = Query(None),
    busca:     Optional[str] = Query(None),
    page:      int = Query(1, ge=1),
    per_page:  int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(403)
    q = select(JurisprudenciaInterna).where(JurisprudenciaInterna.deleted_at.is_(None))
    if area:
        q = q.where(JurisprudenciaInterna.area_juridica.ilike(f"%{area}%"))
    if tribunal:
        q = q.where(JurisprudenciaInterna.tribunal.ilike(f"%{tribunal}%"))
    if resultado:
        q = q.where(JurisprudenciaInterna.resultado == resultado)
    if favorito is not None:
        q = q.where(JurisprudenciaInterna.favorito.is_(favorito))
    if busca:
        t = f"%{busca}%"
        q = q.where(or_(
            JurisprudenciaInterna.titulo.ilike(t),
            JurisprudenciaInterna.ementa.ilike(t),
            JurisprudenciaInterna.tags.ilike(t),
            JurisprudenciaInterna.numero_acordao.ilike(t),
        ))
    q = q.order_by(JurisprudenciaInterna.favorito.desc(), JurisprudenciaInterna.vezes_citada.desc())
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    items = (await db.execute(q.offset((page-1)*per_page).limit(per_page))).scalars().all()
    return {"total": total, "page": page, "per_page": per_page, "items": [_out(j) for j in items]}


@router.post("", status_code=201)
async def criar_jurisprudencia(
    req: JuriIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    j = JurisprudenciaInterna(id=str(uuid4()), created_by=cu.id, **req.model_dump())
    db.add(j)
    await db.commit()
    return _out(j)


@router.get("/{juri_id}")
async def obter_jurisprudencia(
    juri_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(403)
    j = (await db.execute(
        select(JurisprudenciaInterna).where(
            JurisprudenciaInterna.id == juri_id,
            JurisprudenciaInterna.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not j:
        raise HTTPException(404)
    j.vezes_citada = (j.vezes_citada or 0) + 1
    await db.commit()
    return _out(j)


@router.patch("/{juri_id}")
async def atualizar_jurisprudencia(
    juri_id: str,
    req: JuriPatch,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    j = (await db.execute(
        select(JurisprudenciaInterna).where(
            JurisprudenciaInterna.id == juri_id,
            JurisprudenciaInterna.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not j:
        raise HTTPException(404)
    for campo, valor in req.model_dump(exclude_none=True).items():
        setattr(j, campo, valor)
    j.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _out(j)


@router.delete("/{juri_id}", status_code=204)
async def remover_jurisprudencia(
    juri_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        raise HTTPException(403)
    j = (await db.execute(
        select(JurisprudenciaInterna).where(
            JurisprudenciaInterna.id == juri_id,
            JurisprudenciaInterna.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not j:
        raise HTTPException(404)
    j.deleted_at = datetime.now(timezone.utc)
    await db.commit()


@router.post("/{juri_id}/classificar-ia", dependencies=[Depends(rate_limit("juri-classificar-ia", 15))])
async def classificar_com_ia(
    juri_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    IA analisa a ementa e sugere: área jurídica, temas, palavras-chave e aplicabilidade.
    Resultado salvo em classificacao_ia (JSON) — revisão humana recomendada.
    """
    if not _pode_editar(cu):
        raise HTTPException(403)
    j = (await db.execute(
        select(JurisprudenciaInterna).where(
            JurisprudenciaInterna.id == juri_id,
            JurisprudenciaInterna.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not j:
        raise HTTPException(404)

    from app.services.ai_gateway import chat as gw_chat
    import json

    system = """Classifique a ementa jurídica. Responda SOMENTE com JSON válido:
{
  "area": "string",
  "sub_area": "string",
  "temas": ["tema1","tema2"],
  "palavras_chave": ["palavra1","palavra2"],
  "aplicabilidade": "string curta descrevendo quando usar"
}"""
    user_msg = f"EMENTA:\n{j.ementa[:3000]}"

    try:
        resp = await gw_chat(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
            task_type="resumo", temperature=0.1, max_tokens=400,
        )
        classificacao = json.loads(resp.texto)
    except Exception:
        logger.exception("Classificação por IA da jurisprudência falhou")
        raise HTTPException(502, "Classificação por IA indisponível no momento")

    j.classificacao_ia = json.dumps(classificacao, ensure_ascii=False)
    if not j.area_juridica and "area" in classificacao:
        j.area_juridica = classificacao["area"]
    j.updated_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "classificacao": classificacao,
        "modelo": resp.modelo,
        "aviso": "⚠️ Classificação por IA — valide antes de usar.",
    }
