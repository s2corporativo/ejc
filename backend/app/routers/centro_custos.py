# ── app/routers/centro_custos.py ──────────────────────────────────────────────
# Centro de Custos por Processo — lucro real, receitas e despesas por caso.
# Soft-delete arquitetural: lançamentos financeiros nunca são apagados
# fisicamente (deleted_at + auditoria).
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4
from datetime import date as _date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, case as sa_case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.core.ownership import verificar_acesso_caso
from app.models.user import User
from app.models.centro_custo import CentroCusto, CentroCustoTipo, CentroCustoCategoria
from app.models.audit_log import criar_audit_log

router = APIRouter(prefix="/centro-custos", tags=["Centro de Custos"])

_Q2 = Decimal("0.01")


def _money(v) -> Decimal:
    """Coage numérico (Decimal de coluna Numeric, int, float, str, None) para
    Decimal com 2 casas (ROUND_HALF_UP). Lucro/totais ficam Decimal ponta a ponta."""
    return Decimal(str(v or 0)).quantize(_Q2, ROUND_HALF_UP)


# ── Schemas ───────────────────────────────────────────────────────────────────

class CentroCustoIn(BaseModel):
    case_id:         str
    tipo:            CentroCustoTipo
    categoria:       CentroCustoCategoria = CentroCustoCategoria.outros
    valor:           float = Field(gt=0)
    moeda:           str = "BRL"
    descricao:       str = Field(min_length=3)
    data_lancamento: _date
    data_pagamento:  Optional[_date] = None
    pago:            bool = False
    comprovante_id:  Optional[str] = None
    observacoes:     Optional[str] = None


class CentroCustoPatch(BaseModel):
    valor:          Optional[float] = None
    descricao:      Optional[str]  = None
    data_pagamento: Optional[_date] = None
    pago:           Optional[bool] = None
    observacoes:    Optional[str]  = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pode_editar(u: User) -> bool:
    return ROLE_LEVEL.get(u.role.value, 0) >= ROLE_LEVEL["advogado"]

def _out(c: CentroCusto) -> dict:
    return {
        "id": c.id, "case_id": c.case_id,
        "tipo": c.tipo.value if hasattr(c.tipo, "value") else c.tipo,
        "categoria": c.categoria.value if hasattr(c.categoria, "value") else c.categoria,
        "valor": float(c.valor) if c.valor else 0,
        "moeda": c.moeda, "descricao": c.descricao,
        "data_lancamento": c.data_lancamento.isoformat() if c.data_lancamento else None,
        "data_pagamento": c.data_pagamento.isoformat() if c.data_pagamento else None,
        "pago": c.pago, "comprovante_id": c.comprovante_id,
        "observacoes": c.observacoes,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def listar_lancamentos(
    case_id:   Optional[str] = Query(None),
    tipo:      Optional[str] = Query(None),
    categoria: Optional[str] = Query(None),
    pago:      Optional[bool] = Query(None),
    page:      int = Query(1, ge=1),
    per_page:  int = Query(30, ge=1, le=100),
    db:        AsyncSession = Depends(get_db),
    cu:        User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    if case_id:
        await verificar_acesso_caso(db, cu, case_id)
    q = select(CentroCusto).where(CentroCusto.deleted_at.is_(None))
    if case_id:
        q = q.where(CentroCusto.case_id == case_id)
    if tipo:
        q = q.where(CentroCusto.tipo == tipo)
    if categoria:
        q = q.where(CentroCusto.categoria == categoria)
    if pago is not None:
        q = q.where(CentroCusto.pago.is_(pago))
    q = q.order_by(CentroCusto.data_lancamento.desc())
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    items = (await db.execute(q.offset((page-1)*per_page).limit(per_page))).scalars().all()
    return {"total": total, "page": page, "per_page": per_page, "items": [_out(c) for c in items]}


@router.post("", status_code=201)
async def criar_lancamento(
    req: CentroCustoIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    await verificar_acesso_caso(db, cu, req.case_id)
    c = CentroCusto(id=str(uuid4()), created_by=cu.id, **req.model_dump())
    db.add(c)
    await db.commit()
    return _out(c)


@router.get("/caso/{case_id}/resumo")
async def resumo_caso(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Resumo financeiro do caso: total receitas, total despesas, lucro bruto,
    pendências a pagar, breakdown por categoria.
    """
    if not _pode_editar(cu):
        raise HTTPException(403)
    await verificar_acesso_caso(db, cu, case_id)

    row = (await db.execute(
        select(
            func.coalesce(func.sum(
                sa_case((CentroCusto.tipo == CentroCustoTipo.receita, CentroCusto.valor), else_=0)
            ), 0).label("total_receitas"),
            func.coalesce(func.sum(
                sa_case((CentroCusto.tipo == CentroCustoTipo.despesa, CentroCusto.valor), else_=0)
            ), 0).label("total_despesas"),
            func.coalesce(func.sum(
                sa_case(((CentroCusto.tipo == CentroCustoTipo.despesa) & (CentroCusto.pago.is_(False)),
                         CentroCusto.valor), else_=0)
            ), 0).label("pendente_pagar"),
        ).where(CentroCusto.case_id == case_id, CentroCusto.deleted_at.is_(None))
    )).one()

    total_r = _money(row.total_receitas)
    total_d = _money(row.total_despesas)

    # Por categoria
    rows_cat = (await db.execute(
        select(
            CentroCusto.categoria,
            CentroCusto.tipo,
            func.sum(CentroCusto.valor).label("total"),
        )
        .where(CentroCusto.case_id == case_id, CentroCusto.deleted_at.is_(None))
        .group_by(CentroCusto.categoria, CentroCusto.tipo)
        .order_by(func.sum(CentroCusto.valor).desc())
    )).all()

    return {
        "case_id": case_id,
        "total_receitas": total_r,
        "total_despesas": total_d,
        "lucro_bruto":    _money(total_r - total_d),
        "pendente_pagar": _money(row.pendente_pagar),
        "por_categoria": [
            {
                "categoria": r.categoria.value if hasattr(r.categoria, "value") else r.categoria,
                "tipo": r.tipo.value if hasattr(r.tipo, "value") else r.tipo,
                "total": _money(r.total),
            }
            for r in rows_cat
        ],
    }


@router.get("/consolidado")
async def consolidado_geral(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Visão consolidada de todos os casos — exclusivo para sócios.
    Retorna: top 10 casos mais rentáveis, totais globais e pendências.
    """
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        raise HTTPException(403, "Acesso restrito a sócios.")

    # Totais globais
    row = (await db.execute(
        select(
            func.coalesce(func.sum(
                sa_case((CentroCusto.tipo == CentroCustoTipo.receita, CentroCusto.valor), else_=0)
            ), 0).label("total_receitas"),
            func.coalesce(func.sum(
                sa_case((CentroCusto.tipo == CentroCustoTipo.despesa, CentroCusto.valor), else_=0)
            ), 0).label("total_despesas"),
            func.coalesce(func.sum(
                sa_case(((CentroCusto.tipo == CentroCustoTipo.despesa) & (CentroCusto.pago.is_(False)),
                         CentroCusto.valor), else_=0)
            ), 0).label("pendente_pagar"),
        ).where(CentroCusto.deleted_at.is_(None))
    )).one()

    total_r = _money(row.total_receitas)
    total_d = _money(row.total_despesas)

    # Por caso — top 10 mais rentáveis
    rows_caso = (await db.execute(
        select(
            CentroCusto.case_id,
            func.coalesce(func.sum(
                sa_case((CentroCusto.tipo == CentroCustoTipo.receita, CentroCusto.valor), else_=0)
            ), 0).label("receitas"),
            func.coalesce(func.sum(
                sa_case((CentroCusto.tipo == CentroCustoTipo.despesa, CentroCusto.valor), else_=0)
            ), 0).label("despesas"),
        )
        .where(CentroCusto.deleted_at.is_(None))
        .group_by(CentroCusto.case_id)
        .order_by((func.sum(
            sa_case((CentroCusto.tipo == CentroCustoTipo.receita, CentroCusto.valor), else_=0)
        ) - func.sum(
            sa_case((CentroCusto.tipo == CentroCustoTipo.despesa, CentroCusto.valor), else_=0)
        )).desc())
        .limit(10)
    )).all()

    return {
        "global": {
            "total_receitas":  total_r,
            "total_despesas":  total_d,
            "lucro_bruto":     _money(total_r - total_d),
            "pendente_pagar":  _money(row.pendente_pagar),
        },
        "top_casos": [
            {
                "case_id":    r.case_id,
                "receitas":   _money(r.receitas),
                "despesas":   _money(r.despesas),
                "lucro":      _money(_money(r.receitas) - _money(r.despesas)),
            }
            for r in rows_caso
        ],
    }


@router.patch("/{lancamento_id}")
async def atualizar_lancamento(
    lancamento_id: str,
    req: CentroCustoPatch,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    c = (await db.execute(select(CentroCusto).where(
        CentroCusto.id == lancamento_id, CentroCusto.deleted_at.is_(None)
    ))).scalar_one_or_none()
    if not c:
        raise HTTPException(404)
    if c.case_id:
        await verificar_acesso_caso(db, cu, c.case_id)
    for campo, valor in req.model_dump(exclude_none=True).items():
        setattr(c, campo, valor)
    await db.commit()
    return _out(c)


@router.delete("/{lancamento_id}", status_code=204)
async def remover_lancamento(
    lancamento_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        raise HTTPException(403)
    c = (await db.execute(select(CentroCusto).where(
        CentroCusto.id == lancamento_id, CentroCusto.deleted_at.is_(None)
    ))).scalar_one_or_none()
    if not c:
        raise HTTPException(404)
    # Soft-delete (arquitetural): nunca apagar lançamento financeiro fisicamente
    c.deleted_at = datetime.now(timezone.utc)
    await criar_audit_log(
        db, cu.id, cu.role.value, "DELETE", "centro_custos", lancamento_id,
        detalhes=f"Lançamento {c.tipo} de {float(c.valor):.2f} {c.moeda} no caso {c.case_id}",
    )
    await db.commit()
