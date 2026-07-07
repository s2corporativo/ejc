# ── app/routers/atendimentos.py ────────────────────────────────────────────────
# Histórico de atendimentos ao cliente — CRM básico jurídico.
# Fase 4: adicionados advogado_responsavel_id, duracao_horas, satisfacao_cliente
#         e endpoints de gestão por advogado.
from __future__ import annotations
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.core.ownership import verificar_acesso_caso
from app.models.user import User
from app.models.atendimento import Atendimento, AtendimentoTipo
from app.modules.auditoria.middleware import registrar_acao

router = APIRouter(prefix="/atendimentos", tags=["Atendimentos"])

# ── Schemas ───────────────────────────────────────────────────────────────────

class AtendimentoIn(BaseModel):
    client_id:               str
    case_id:                 Optional[str]   = None
    tipo:                    AtendimentoTipo
    data_atendimento:        datetime
    duracao_min:             Optional[str]   = None
    resumo:                  str = Field(min_length=10)
    proximo_passo:           Optional[str]   = None
    observacoes_privadas:    Optional[str]   = None
    # Novos campos — gestão por advogado
    advogado_responsavel_id: Optional[str]   = None
    duracao_horas:           Optional[float] = Field(None, ge=0, le=24)
    satisfacao_cliente:      Optional[int]   = Field(None, ge=1, le=5)


class AtendimentoPatch(BaseModel):
    tipo:                    Optional[AtendimentoTipo] = None
    data_atendimento:        Optional[datetime]        = None
    duracao_min:             Optional[str]             = None
    resumo:                  Optional[str]             = None
    proximo_passo:           Optional[str]             = None
    observacoes_privadas:    Optional[str]             = None
    advogado_responsavel_id: Optional[str]             = None
    duracao_horas:           Optional[float]           = None
    satisfacao_cliente:      Optional[int]             = Field(None, ge=1, le=5)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_staff(user: User) -> bool:
    # CRM/relacionamento é operado também por secretaria.
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["secretaria"]

def _pode_ver_privado(user: User) -> bool:
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["advogado"]

def _out(a: Atendimento, com_privado: bool = True) -> dict:
    return {
        "id":                     a.id,
        "client_id":              a.client_id,
        "case_id":                a.case_id,
        "tipo":                   a.tipo.value if hasattr(a.tipo, "value") else a.tipo,
        "data_atendimento":       a.data_atendimento.isoformat() if a.data_atendimento else None,
        "duracao_min":            a.duracao_min,
        "duracao_horas":          float(a.duracao_horas) if a.duracao_horas is not None else None,
        "resumo":                 a.resumo,
        "proximo_passo":          a.proximo_passo,
        "observacoes_privadas":   a.observacoes_privadas if com_privado else None,
        "advogado_responsavel_id": a.advogado_responsavel_id,
        "satisfacao_cliente":     a.satisfacao_cliente,
        "created_by":             a.created_by,
        "created_at":             a.created_at.isoformat() if a.created_at else None,
    }


# ── Endpoints base ─────────────────────────────────────────────────────────────


async def _check_atendimento_ownership(atendimento_id: str, cu, db) -> object:
    """Verifica se o usuário tem acesso ao atendimento."""
    from sqlalchemy import select
    from app.models.atendimento import Atendimento
    from fastapi import HTTPException
    from app.core.security import ROLE_LEVEL
    atend = (await db.execute(
        select(Atendimento).where(Atendimento.id == atendimento_id)
    )).scalar_one_or_none()
    if not atend:
        raise HTTPException(404, "Atendimento não encontrado")
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        if atend.created_by != cu.id and atend.advogado_responsavel_id != cu.id:
            raise HTTPException(403, "Sem permissão para este atendimento")
    return atend


@router.get("")
async def listar_atendimentos(
    client_id:  Optional[str] = Query(None),
    case_id:    Optional[str] = Query(None),
    tipo:       Optional[str] = Query(None),
    advogado_id: Optional[str] = Query(None),
    page:       int = Query(1, ge=1),
    per_page:   int = Query(20, ge=1, le=100),
    db:         AsyncSession = Depends(get_db),
    cu:         User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(403)
    q = select(Atendimento)
    if client_id:
        q = q.where(Atendimento.client_id == client_id)
    if case_id:
        q = q.where(Atendimento.case_id == case_id)
    if tipo:
        q = q.where(Atendimento.tipo == tipo)
    if advogado_id:
        q = q.where(Atendimento.advogado_responsavel_id == advogado_id)
    q = q.order_by(Atendimento.data_atendimento.desc())
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    items = (await db.execute(q.offset((page - 1) * per_page).limit(per_page))).scalars().all()
    priv  = _pode_ver_privado(cu)
    return {"total": total, "page": page, "per_page": per_page,
            "items": [_out(a, com_privado=priv) for a in items]}


@router.post("", status_code=201)
async def criar_atendimento(
    req: AtendimentoIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(403)
    if req.case_id:
        await verificar_acesso_caso(db, cu, req.case_id)
    data = req.model_dump()
    # Se não informado o advogado responsável, assume o criador
    if not data.get("advogado_responsavel_id"):
        data["advogado_responsavel_id"] = cu.id
    a = Atendimento(id=str(uuid4()), created_by=cu.id, **data)
    db.add(a)
    await db.commit()
    await registrar_acao(
        db, cu.id, "criar", "atendimentos", a.id,
        f"Atendimento {a.tipo} registrado para cliente {a.client_id}",
    )
    return _out(a)


@router.get("/meus")
async def meus_atendimentos(
    page:     int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db:       AsyncSession = Depends(get_db),
    cu:       User = Depends(get_current_user),
):
    """Atendimentos em que o usuário autenticado é o advogado responsável."""
    if not _is_staff(cu):
        raise HTTPException(403)
    q = (select(Atendimento)
         .where(Atendimento.advogado_responsavel_id == cu.id)
         .order_by(Atendimento.data_atendimento.desc()))
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    items = (await db.execute(q.offset((page - 1) * per_page).limit(per_page))).scalars().all()
    return {"total": total, "page": page, "per_page": per_page,
            "items": [_out(a) for a in items]}


@router.get("/por-advogado/{advogado_id}")
async def por_advogado(
    advogado_id: str,
    page:        int = Query(1, ge=1),
    per_page:    int = Query(20, ge=1, le=100),
    db:          AsyncSession = Depends(get_db),
    cu:          User = Depends(get_current_user),
):
    """Lista todos os atendimentos de um advogado específico (somente sócios ou o próprio)."""
    nivel = ROLE_LEVEL.get(cu.role.value, 0)
    if nivel < ROLE_LEVEL["secretaria"]:
        raise HTTPException(403)
    if advogado_id != cu.id and nivel < ROLE_LEVEL["socio"]:
        raise HTTPException(403, "Somente sócios podem ver atendimentos de outros advogados.")

    q = (select(Atendimento)
         .where(Atendimento.advogado_responsavel_id == advogado_id)
         .order_by(Atendimento.data_atendimento.desc()))
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    items = (await db.execute(q.offset((page - 1) * per_page).limit(per_page))).scalars().all()
    return {"total": total, "page": page, "per_page": per_page,
            "items": [_out(a) for a in items]}


@router.get("/dashboard")
async def dashboard_atendimentos(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Estatísticas agregadas por advogado responsável.
    Somente sócios visualizam todos; demais veem apenas o próprio.
    """
    if not _is_staff(cu):
        raise HTTPException(403)

    nivel = ROLE_LEVEL.get(cu.role.value, 0)
    q_base = select(
        Atendimento.advogado_responsavel_id,
        func.count(Atendimento.id).label("total"),
        func.coalesce(func.sum(Atendimento.duracao_horas), 0).label("total_horas"),
        func.coalesce(func.avg(Atendimento.satisfacao_cliente), 0).label("satisfacao_media"),
    ).group_by(Atendimento.advogado_responsavel_id)

    if nivel < ROLE_LEVEL["socio"]:
        q_base = q_base.where(Atendimento.advogado_responsavel_id == cu.id)

    rows = (await db.execute(q_base)).all()
    return [
        {
            "advogado_id":      r.advogado_responsavel_id,
            "total_atendimentos": r.total,
            "total_horas":      round(float(r.total_horas), 2),
            "satisfacao_media": round(float(r.satisfacao_media), 2),
        }
        for r in rows
    ]


@router.get("/stats")
async def stats_mensais(
    ano:  int = Query(default=2026),
    db:   AsyncSession = Depends(get_db),
    cu:   User = Depends(get_current_user),
):
    """Breakdown mensal de atendimentos — quantidade e horas por mês."""
    if not _is_staff(cu):
        raise HTTPException(403)

    from sqlalchemy import extract
    nivel = ROLE_LEVEL.get(cu.role.value, 0)
    q = (select(
        extract("month", Atendimento.data_atendimento).label("mes"),
        func.count(Atendimento.id).label("total"),
        func.coalesce(func.sum(Atendimento.duracao_horas), 0).label("total_horas"),
        func.coalesce(func.avg(Atendimento.satisfacao_cliente), 0).label("satisfacao_media"),
    )
    .where(extract("year", Atendimento.data_atendimento) == ano)
    .group_by(extract("month", Atendimento.data_atendimento))
    .order_by(extract("month", Atendimento.data_atendimento)))

    if nivel < ROLE_LEVEL["socio"]:
        q = q.where(Atendimento.advogado_responsavel_id == cu.id)

    rows = (await db.execute(q)).all()
    MESES = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
    return [
        {
            "mes":     int(r.mes),
            "mes_nome": MESES[int(r.mes) - 1],
            "total":   r.total,
            "total_horas": round(float(r.total_horas), 2),
            "satisfacao_media": round(float(r.satisfacao_media), 2),
        }
        for r in rows
    ]


# ── Endpoints individuais ──────────────────────────────────────────────────────

@router.get("/{atendimento_id}")
async def obter_atendimento(
    atendimento_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(403)
    a = await _check_atendimento_ownership(atendimento_id, cu, db)
    return _out(a, com_privado=_pode_ver_privado(cu))


@router.patch("/{atendimento_id}")
async def atualizar_atendimento(
    atendimento_id: str,
    req: AtendimentoPatch,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(403)
    a = await _check_atendimento_ownership(atendimento_id, cu, db)
    for campo, valor in req.model_dump(exclude_none=True).items():
        setattr(a, campo, valor)
    a.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _out(a)


@router.delete("/{atendimento_id}", status_code=204)
async def remover_atendimento(
    atendimento_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["advogado"]:
        raise HTTPException(403)
    a = await _check_atendimento_ownership(atendimento_id, cu, db)
    await db.delete(a)
    await db.commit()
