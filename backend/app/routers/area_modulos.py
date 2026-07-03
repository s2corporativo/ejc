# ── app/routers/area_modulos.py ───────────────────────────────────────────────
# Matriz área do direito → módulos/ferramentas (R6 — antes hardcoded).
# Leitura: usuários internos (frontend usa para sugerir módulos ao classificar caso).
# Escrita: admin/socio, com audit log e UNIQUE(area, module_key) → 409 amigável.
from __future__ import annotations
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.redesign import AreaModuloMapping
from app.models.user import User
from app.modules.auditoria.middleware import registrar_acao
from app.schemas.redesign import AreaModuloCreate, AreaModuloUpdate

router = APIRouter(prefix="/area-modulos", tags=["Matriz Área → Módulos"])

_gestores = require_roles(["admin", "socio"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _somente_interno(cu: User) -> None:
    """Defesa em profundidade: cliente_externo já é confinado a /api/portal/*
    pelo AuthMiddleware, mas barramos explicitamente aqui também."""
    if cu.role == "cliente_externo":
        raise HTTPException(403, "Acesso restrito a usuários internos")


def _out(m: AreaModuloMapping) -> dict:
    return {
        "id": m.id,
        "area_juridica": m.area_juridica,
        "module_key": m.module_key,
        "habilitado": m.habilitado,
        "ordem": m.ordem,
        "ferramentas": m.ferramentas or [],
        "workflow_template_id": m.workflow_template_id,
        "checklist_template_id": m.checklist_template_id,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    }


async def _get_or_404(db: AsyncSession, mapping_id: str) -> AreaModuloMapping:
    m = (await db.execute(
        select(AreaModuloMapping).where(AreaModuloMapping.id == mapping_id)
    )).scalar_one_or_none()
    if not m:
        raise HTTPException(404, "Mapeamento área→módulo não encontrado")
    return m


async def _existe_duplicado(db: AsyncSession, area: str, module_key: str,
                            ignorar_id: str | None = None) -> bool:
    stmt = select(AreaModuloMapping.id).where(
        AreaModuloMapping.area_juridica == area,
        AreaModuloMapping.module_key == module_key,
    )
    if ignorar_id:
        stmt = stmt.where(AreaModuloMapping.id != ignorar_id)
    return (await db.execute(stmt.limit(1))).scalar_one_or_none() is not None


def _erro_409(area: str, module_key: str) -> HTTPException:
    return HTTPException(
        409,
        f"O módulo '{module_key}' já está mapeado para a área '{area}'. "
        "Edite o registro existente (PATCH) em vez de criar um duplicado.",
    )


async def _tratar_integrity_error(db: AsyncSession, exc: IntegrityError,
                                  area: str, module_key: str) -> None:
    await db.rollback()
    if "uq_area_modulos_area_module" in str(exc.orig):
        raise _erro_409(area, module_key)
    raise HTTPException(
        422,
        "Referência inválida: workflow_template_id ou checklist_template_id inexistente",
    )


# ── Endpoints — Leitura (usuários internos) ───────────────────────────────────

@router.get("/")
async def matriz_completa(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Matriz completa agrupada por area_juridica (inclui não habilitados)."""
    _somente_interno(cu)
    rows = (await db.execute(
        select(AreaModuloMapping).order_by(
            AreaModuloMapping.area_juridica,
            AreaModuloMapping.ordem,
            AreaModuloMapping.module_key,
        )
    )).scalars().all()
    grupos: dict[str, list[dict]] = {}
    for m in rows:
        grupos.setdefault(m.area_juridica, []).append(_out(m))
    return [{"area_juridica": area, "modulos": modulos}
            for area, modulos in grupos.items()]


@router.get("/{area}")
async def modulos_da_area(
    area: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Módulos habilitados da área, com ferramentas — usado pelo frontend
    para sugerir módulos ao classificar um caso."""
    _somente_interno(cu)
    area_slug = area.strip().strip("/").lower()
    rows = (await db.execute(
        select(AreaModuloMapping).where(
            AreaModuloMapping.area_juridica == area_slug,
            AreaModuloMapping.habilitado == True,  # noqa: E712
        ).order_by(AreaModuloMapping.ordem, AreaModuloMapping.module_key)
    )).scalars().all()
    return {"area_juridica": area_slug, "modulos": [_out(m) for m in rows]}


# ── Endpoints — Escrita (admin/socio) ─────────────────────────────────────────

@router.post("/", status_code=201)
async def criar_mapeamento(
    req: AreaModuloCreate,
    db:  AsyncSession = Depends(get_db),
    cu:  User = Depends(_gestores),
):
    if await _existe_duplicado(db, req.area_juridica, req.module_key):
        raise _erro_409(req.area_juridica, req.module_key)

    m = AreaModuloMapping(id=str(uuid4()), **req.model_dump())
    db.add(m)
    try:
        await db.commit()
    except IntegrityError as exc:
        await _tratar_integrity_error(db, exc, req.area_juridica, req.module_key)
    await registrar_acao(db, cu.id, "criar", "area_modulos", m.id,
                         f"Módulo '{m.module_key}' mapeado para a área '{m.area_juridica}'")
    return _out(m)


@router.patch("/{mapping_id}")
async def atualizar_mapeamento(
    mapping_id: str,
    req: AreaModuloUpdate,
    db:  AsyncSession = Depends(get_db),
    cu:  User = Depends(_gestores),
):
    m = await _get_or_404(db, mapping_id)
    data = req.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(422, "Nenhum campo para atualizar")

    nova_area = data.get("area_juridica", m.area_juridica)
    novo_mk   = data.get("module_key", m.module_key)
    if ("area_juridica" in data or "module_key" in data) and \
            await _existe_duplicado(db, nova_area, novo_mk, ignorar_id=m.id):
        raise _erro_409(nova_area, novo_mk)

    for campo, valor in data.items():
        setattr(m, campo, valor)
    try:
        await db.commit()
    except IntegrityError as exc:
        await _tratar_integrity_error(db, exc, nova_area, novo_mk)
    await registrar_acao(db, cu.id, "atualizar", "area_modulos", m.id,
                         f"Mapeamento '{m.area_juridica}' → '{m.module_key}' "
                         f"atualizado ({', '.join(sorted(data))})")
    return _out(m)


@router.delete("/{mapping_id}", status_code=204)
async def remover_mapeamento(
    mapping_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_gestores),
):
    """Remove o mapeamento (hard delete — a tabela não tem soft delete;
    o estado anterior fica preservado no audit log via dados_antes)."""
    m = await _get_or_404(db, mapping_id)
    antes = _out(m)
    await db.delete(m)
    await db.commit()
    await registrar_acao(db, cu.id, "excluir", "area_modulos", mapping_id,
                         f"Mapeamento '{antes['area_juridica']}' → '{antes['module_key']}' removido",
                         dados_antes=antes)
