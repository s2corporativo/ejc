# ── app/routers/module_help.py ────────────────────────────────────────────────
# Ajuda contextual por módulo (botão "?" por tela — F4/R1).
# Leitura: qualquer usuário interno autenticado (cliente_externo NÃO).
# Escrita: admin/socio, com audit log e soft delete (ativo=False).
from __future__ import annotations
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.redesign import ModuleHelp
from app.models.user import User
from app.modules.auditoria.middleware import registrar_acao
from app.schemas.redesign import ModuleHelpCreate, ModuleHelpUpdate

router = APIRouter(prefix="/module-help", tags=["Ajuda de Módulos"])

_gestores = require_roles(["admin", "socio"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _somente_interno(cu: User) -> None:
    """Defesa em profundidade: cliente_externo já é confinado a /api/portal/*
    pelo AuthMiddleware, mas barramos explicitamente aqui também."""
    if cu.role == "cliente_externo":
        raise HTTPException(403, "Acesso restrito a usuários internos")


def _out(h: ModuleHelp) -> dict:
    return {
        "id": h.id,
        "module_key": h.module_key,
        "titulo": h.titulo,
        "conteudo_md": h.conteudo_md,
        "ordem": h.ordem,
        "ativo": h.ativo,
        "atualizado_por": h.atualizado_por,
        "created_at": h.created_at.isoformat() if h.created_at else None,
        "updated_at": h.updated_at.isoformat() if h.updated_at else None,
    }


async def _get_or_404(db: AsyncSession, help_id: str) -> ModuleHelp:
    h = (await db.execute(
        select(ModuleHelp).where(ModuleHelp.id == help_id)
    )).scalar_one_or_none()
    if not h:
        raise HTTPException(404, "Tópico de ajuda não encontrado")
    return h


# ── Endpoints — Leitura (usuários internos) ───────────────────────────────────

@router.get("/")
async def buscar_ajuda(
    q:  Optional[str] = Query(None, min_length=2, max_length=120,
                              description='Busca "como fazer X" em título e conteúdo'),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Lista tópicos ativos; com `q`, busca ILIKE em titulo e conteudo_md."""
    _somente_interno(cu)
    stmt = select(ModuleHelp).where(ModuleHelp.ativo == True)  # noqa: E712
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(
            ModuleHelp.titulo.ilike(like),
            ModuleHelp.conteudo_md.ilike(like),
        ))
    rows = (await db.execute(
        stmt.order_by(ModuleHelp.module_key, ModuleHelp.ordem)
    )).scalars().all()
    return [_out(h) for h in rows]


@router.get("/{module_key:path}")
async def ajuda_do_modulo(
    module_key: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Tópicos ativos do módulo, ordenados por `ordem`.

    `:path` permite chaves com barra (ex.: "ramos/civel")."""
    _somente_interno(cu)
    rows = (await db.execute(
        select(ModuleHelp).where(
            ModuleHelp.module_key == module_key.strip().strip("/").lower(),
            ModuleHelp.ativo == True,  # noqa: E712
        ).order_by(ModuleHelp.ordem)
    )).scalars().all()
    return [_out(h) for h in rows]


# ── Endpoints — Escrita (admin/socio) ─────────────────────────────────────────

@router.post("/", status_code=201)
async def criar_ajuda(
    req: ModuleHelpCreate,
    db:  AsyncSession = Depends(get_db),
    cu:  User = Depends(_gestores),
):
    h = ModuleHelp(id=str(uuid4()), atualizado_por=cu.id, **req.model_dump())
    db.add(h)
    await db.commit()
    await registrar_acao(db, cu.id, "criar", "module_help", h.id,
                         f"Ajuda '{h.titulo}' criada no módulo '{h.module_key}'")
    return _out(h)


@router.patch("/{help_id}")
async def atualizar_ajuda(
    help_id: str,
    req: ModuleHelpUpdate,
    db:  AsyncSession = Depends(get_db),
    cu:  User = Depends(_gestores),
):
    h = await _get_or_404(db, help_id)
    data = req.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(422, "Nenhum campo para atualizar")
    for campo, valor in data.items():
        setattr(h, campo, valor)
    h.atualizado_por = cu.id
    await db.commit()
    await registrar_acao(db, cu.id, "atualizar", "module_help", h.id,
                         f"Ajuda '{h.titulo}' atualizada ({', '.join(sorted(data))})")
    return _out(h)


@router.delete("/{help_id}", status_code=204)
async def desativar_ajuda(
    help_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_gestores),
):
    """Soft delete: marca ativo=False (conteúdo preservado para auditoria)."""
    h = await _get_or_404(db, help_id)
    h.ativo = False
    h.atualizado_por = cu.id
    await db.commit()
    await registrar_acao(db, cu.id, "desativar", "module_help", h.id,
                         f"Ajuda '{h.titulo}' desativada (soft delete)")
