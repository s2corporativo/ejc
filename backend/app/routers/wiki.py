"""
wiki.py — Wiki interna do escritório (#93). CRUD de páginas editáveis
(procedimentos, tabela de honorários, contatos, etc.). Sem IA.
"""
from __future__ import annotations
import re
import unicodedata
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.user import User
from app.models.wiki import WikiPagina

router = APIRouter(prefix="/wiki", tags=["Wiki Interna"])


def _role_level(user: User) -> int:
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    return ROLE_LEVEL.get(role, 0)


def _exigir_staff(user: User) -> None:
    # Wiki interna do escritório: leitura restrita a staff (estagiário+).
    # cliente_externo já é barrado pelo AuthMiddleware — defesa em profundidade.
    if _role_level(user) < ROLE_LEVEL["estagiario"]:
        raise HTTPException(403, "Acesso restrito")


def _exigir_editor(user: User) -> None:
    # Escrita (criar/editar) exige advogado+; exclusão permanece socio+.
    if _role_level(user) < ROLE_LEVEL["advogado"]:
        raise HTTPException(403, "Acesso restrito")


def _slug(titulo: str) -> str:
    t = unicodedata.normalize("NFKD", titulo or "").encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return t[:200] or "pagina"


class WikiIn(BaseModel):
    titulo: str = Field(..., min_length=2, max_length=255)
    categoria: str | None = Field(None, max_length=60)
    conteudo: str | None = None


@router.get("")
async def listar(categoria: str | None = None, db: AsyncSession = Depends(get_db),
                 cu: User = Depends(get_current_user)):
    _exigir_staff(cu)
    q = select(WikiPagina).where(WikiPagina.deleted_at.is_(None))
    if categoria:
        q = q.where(WikiPagina.categoria == categoria)
    rows = (await db.execute(q.order_by(WikiPagina.categoria, WikiPagina.titulo))).scalars().all()
    return [{"id": w.id, "titulo": w.titulo, "slug": w.slug, "categoria": w.categoria,
             "atualizado_em": w.updated_at} for w in rows]


@router.get("/{pid}")
async def obter(pid: str, db: AsyncSession = Depends(get_db),
                cu: User = Depends(get_current_user)):
    _exigir_staff(cu)
    w = (await db.execute(select(WikiPagina).where(
        WikiPagina.id == pid, WikiPagina.deleted_at.is_(None)))).scalar_one_or_none()
    if not w:
        raise HTTPException(404, "Página não encontrada")
    return {"id": w.id, "titulo": w.titulo, "slug": w.slug, "categoria": w.categoria,
            "conteudo": w.conteudo, "atualizado_em": w.updated_at}


@router.post("", status_code=201)
async def criar(body: WikiIn, db: AsyncSession = Depends(get_db),
                cu: User = Depends(get_current_user)):
    _exigir_editor(cu)
    w = WikiPagina(id=str(uuid4()), titulo=body.titulo, slug=_slug(body.titulo),
                   categoria=body.categoria, conteudo=body.conteudo, atualizado_por=cu.id)
    db.add(w)
    await db.commit()
    return {"id": w.id, "slug": w.slug, "detail": "Página criada"}


@router.patch("/{pid}")
async def editar(pid: str, body: WikiIn, db: AsyncSession = Depends(get_db),
                 cu: User = Depends(get_current_user)):
    _exigir_editor(cu)
    w = (await db.execute(select(WikiPagina).where(
        WikiPagina.id == pid, WikiPagina.deleted_at.is_(None)))).scalar_one_or_none()
    if not w:
        raise HTTPException(404, "Página não encontrada")
    w.titulo = body.titulo
    w.slug = _slug(body.titulo)
    w.categoria = body.categoria
    w.conteudo = body.conteudo
    w.atualizado_por = cu.id
    await db.commit()
    return {"id": w.id, "detail": "Página atualizada"}


@router.delete("/{pid}")
async def excluir(pid: str, db: AsyncSession = Depends(get_db),
                  cu: User = Depends(get_current_user)):
    role = cu.role.value if hasattr(cu.role, "value") else str(cu.role)
    if role not in ("superadmin", "admin", "socio"):
        raise HTTPException(403, "Acesso restrito")
    w = (await db.execute(select(WikiPagina).where(
        WikiPagina.id == pid, WikiPagina.deleted_at.is_(None)))).scalar_one_or_none()
    if not w:
        raise HTTPException(404, "Página não encontrada")
    w.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return {"detail": "Página removida"}
