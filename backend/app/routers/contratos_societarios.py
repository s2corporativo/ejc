# ── app/routers/contratos_societarios.py ─────────────────────────────────────
# Gestão de Contratos Societários — CRUD + ciclo de vida + alertas.
from __future__ import annotations
from uuid import uuid4
from datetime import datetime, timezone, date as _date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.user import User
from app.models.contrato_societario import (
    ContratoSocietario, ContratoHistorico,
    StatusContrato, TipoContrato,
)
from app.modules.auditoria.middleware import registrar_acao

router = APIRouter(prefix="/contratos", tags=["Contratos Societários"])

_TRANSICOES_VALIDAS: dict[str, list[str]] = {
    "rascunho":   ["em_revisao", "rescindido"],
    "em_revisao": ["aprovado", "rascunho", "rescindido"],
    "aprovado":   ["assinado", "rascunho", "rescindido"],
    "assinado":   ["vigente", "rescindido"],
    "vigente":    ["suspenso", "expirado", "rescindido"],
    "suspenso":   ["vigente", "rescindido"],
    "expirado":   ["vigente", "rescindido"],
    "rescindido": [],
}


class ContratoIn(BaseModel):
    titulo:                    str = Field(min_length=3, max_length=300)
    tipo:                      TipoContrato
    objeto:                    str = Field(min_length=10)
    partes:                    Optional[str] = None
    clausulas_especiais:       Optional[str] = None
    valor_total:               Optional[float] = None
    moeda:                     str = "BRL"
    periodicidade:             Optional[str] = None
    data_assinatura:           Optional[_date] = None
    data_inicio:               Optional[_date] = None
    data_fim:                  Optional[_date] = None
    renovacao_automatica:      bool = False
    prazo_aviso_rescisao_dias: int = 30
    alertar_dias_antes:        int = 60
    case_id:                   Optional[str] = None
    client_id:                 Optional[str] = None
    documento_id:              Optional[str] = None
    observacoes:               Optional[str] = None
    tags:                      Optional[str] = None


class ContratoPatch(BaseModel):
    titulo:               Optional[str] = None
    partes:               Optional[str] = None
    objeto:               Optional[str] = None
    valor_total:          Optional[float] = None
    data_inicio:          Optional[_date] = None
    data_fim:             Optional[_date] = None
    renovacao_automatica: Optional[bool] = None
    alertar_dias_antes:   Optional[int] = None
    observacoes:          Optional[str] = None
    tags:                 Optional[str] = None


class TransicaoReq(BaseModel):
    novo_status: StatusContrato
    observacao:  Optional[str] = None


def _pode_editar(u: User) -> bool:
    return ROLE_LEVEL.get(u.role.value, 0) >= ROLE_LEVEL["advogado"]

def _out(c: ContratoSocietario) -> dict:
    return {
        "id": c.id, "titulo": c.titulo,
        "tipo": c.tipo.value if hasattr(c.tipo, "value") else c.tipo,
        "status": c.status.value if hasattr(c.status, "value") else c.status,
        "objeto": c.objeto, "partes": c.partes,
        "valor_total": float(c.valor_total) if c.valor_total else None,
        "moeda": c.moeda, "periodicidade": c.periodicidade,
        "data_inicio": c.data_inicio.isoformat() if c.data_inicio else None,
        "data_fim": c.data_fim.isoformat() if c.data_fim else None,
        "renovacao_automatica": c.renovacao_automatica,
        "alertar_dias_antes": c.alertar_dias_antes,
        "case_id": c.case_id, "client_id": c.client_id,
        "tags": c.tags, "observacoes": c.observacoes,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.get("")
async def listar_contratos(
    status:    Optional[str] = Query(None),
    tipo:      Optional[str] = Query(None),
    client_id: Optional[str] = Query(None),
    busca:     Optional[str] = Query(None),
    vencendo:  int = Query(0, ge=0),   # próximos N dias (0 = sem filtro)
    page:      int = Query(1, ge=1),
    per_page:  int = Query(20, ge=1, le=100),
    db:        AsyncSession = Depends(get_db),
    cu:        User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    q = select(ContratoSocietario).where(ContratoSocietario.deleted_at.is_(None))
    if status:
        q = q.where(ContratoSocietario.status == status)
    if tipo:
        q = q.where(ContratoSocietario.tipo == tipo)
    if client_id:
        q = q.where(ContratoSocietario.client_id == client_id)
    if busca:
        t = f"%{busca}%"
        q = q.where(or_(ContratoSocietario.titulo.ilike(t), ContratoSocietario.partes.ilike(t)))
    if vencendo > 0:
        from datetime import date as _date_cls, timedelta
        limite = _date_cls.today() + timedelta(days=vencendo)
        q = q.where(ContratoSocietario.data_fim <= limite, ContratoSocietario.data_fim >= _date_cls.today())
    q = q.order_by(ContratoSocietario.data_fim.asc().nullslast())
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    items = (await db.execute(q.offset((page-1)*per_page).limit(per_page))).scalars().all()
    return {"total": total, "page": page, "per_page": per_page, "items": [_out(c) for c in items]}


@router.post("", status_code=201)
async def criar_contrato(
    req: ContratoIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    c = ContratoSocietario(id=str(uuid4()), created_by=cu.id, **req.model_dump())
    db.add(c)
    await db.commit()
    await registrar_acao(db, cu.id, "criar", "contratos", c.id, f"Contrato '{c.titulo}' criado")
    return _out(c)


@router.get("/{contrato_id}")
async def obter_contrato(
    contrato_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    c = (await db.execute(
        select(ContratoSocietario).where(
            ContratoSocietario.id == contrato_id,
            ContratoSocietario.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not c:
        raise HTTPException(404)
    historico = (await db.execute(
        select(ContratoHistorico).where(ContratoHistorico.contrato_id == contrato_id)
        .order_by(ContratoHistorico.alterado_em.desc())
    )).scalars().all()
    return {
        **_out(c),
        "historico": [
            {"status_de": h.status_de, "status_para": h.status_para,
             "observacao": h.observacao,
             "alterado_em": h.alterado_em.isoformat() if h.alterado_em else None}
            for h in historico
        ]
    }


@router.patch("/{contrato_id}")
async def atualizar_contrato(
    contrato_id: str,
    req: ContratoPatch,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    c = (await db.execute(
        select(ContratoSocietario).where(
            ContratoSocietario.id == contrato_id,
            ContratoSocietario.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not c:
        raise HTTPException(404)
    for campo, valor in req.model_dump(exclude_none=True).items():
        setattr(c, campo, valor)
    c.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _out(c)


@router.post("/{contrato_id}/transicao")
async def transicionar_status(
    contrato_id: str,
    req: TransicaoReq,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Avança o ciclo de vida do contrato. Transições inválidas são rejeitadas."""
    if not _pode_editar(cu):
        raise HTTPException(403)
    c = (await db.execute(
        select(ContratoSocietario).where(
            ContratoSocietario.id == contrato_id,
            ContratoSocietario.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not c:
        raise HTTPException(404)

    status_atual = c.status.value if hasattr(c.status, "value") else c.status
    novo = req.novo_status.value if hasattr(req.novo_status, "value") else req.novo_status
    permitidos = _TRANSICOES_VALIDAS.get(status_atual, [])
    if novo not in permitidos:
        raise HTTPException(422, f"Transição '{status_atual}' → '{novo}' não permitida. Permitidas: {permitidos}")

    hist = ContratoHistorico(
        id=str(uuid4()), contrato_id=contrato_id,
        status_de=status_atual, status_para=novo,
        observacao=req.observacao, alterado_por=cu.id,
    )
    db.add(hist)
    c.status = req.novo_status
    c.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await registrar_acao(db, cu.id, "transicao", "contratos", c.id,
                         f"Status: {status_atual} → {novo}")
    return _out(c)


@router.delete("/{contrato_id}", status_code=204)
async def arquivar_contrato(
    contrato_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        raise HTTPException(403)
    c = (await db.execute(
        select(ContratoSocietario).where(
            ContratoSocietario.id == contrato_id,
            ContratoSocietario.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not c:
        raise HTTPException(404)
    c.deleted_at = datetime.now(timezone.utc)
    await db.commit()
