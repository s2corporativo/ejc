from app.core.pagination import executar_pagina
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
from app.core.ownership import verificar_acesso_caso, is_gestao
from app.models.user import User
from app.models.centro_custo import CentroCusto, CentroCustoTipo, CentroCustoCategoria
from app.models.audit_log import criar_audit_log
from app.services.document_access_policy import exigir_documento_compativel_com_caso
from app.services.finance_governance import (
    competencia_de_data,
    exigir_competencia_aberta,
    limite_dupla_aprovacao,
    solicitar_ou_consumir_aprovacao,
)

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


from app.core.ownership import ids_casos_do_usuario as _ids_casos_visiveis


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
    elif not is_gestao(cu):
        # Sem case_id: equipe não-gestão (advogado — financeiro/estagiario já
        # barrados por _pode_editar) vê só custos dos próprios casos; antes
        # listava lançamentos de TODOS os casos (IDOR de leitura). Mesmo padrão
        # de subquery de casos-do-usuário de fees._ids_casos_do_usuario; aqui o
        # limiar de visão total é gestão (socio+). Gestão segue vendo tudo.
        q = q.where(CentroCusto.case_id.in_(_ids_casos_visiveis(cu)))
    if tipo:
        q = q.where(CentroCusto.tipo == tipo)
    if categoria:
        q = q.where(CentroCusto.categoria == categoria)
    if pago is not None:
        q = q.where(CentroCusto.pago.is_(pago))
    q = q.order_by(CentroCusto.data_lancamento.desc())
    total, items = await executar_pagina(db, q, page, per_page)
    total = total or 0
    return {"total": total, "page": page, "per_page": per_page, "items": [_out(c) for c in items]}


@router.post("", status_code=201)
async def criar_lancamento(
    req: CentroCustoIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)

    # Acesso ao caso é provado uma única vez e o objeto autorizado é reutilizado
    # na validação do comprovante. Documento de outro caso/cliente ou de cofre
    # acima do papel atual falha fechado antes de qualquer escrita financeira.
    case = await verificar_acesso_caso(db, cu, req.case_id)
    if req.comprovante_id:
        await exigir_documento_compativel_com_caso(
            db,
            cu,
            document_id=req.comprovante_id,
            case=case,
        )

    competencia = competencia_de_data(
        req.data_pagamento if req.pago else req.data_lancamento
    )
    await exigir_competencia_aberta(
        db, competencia, "Criar lançamento no centro de custos"
    )
    dados = req.model_dump()
    approval_required = False
    if req.pago:
        limite = await limite_dupla_aprovacao(db)
        if Decimal(str(req.valor)) >= limite:
            dados["pago"] = False
            dados["data_pagamento"] = None
            approval_required = True

    c = CentroCusto(id=str(uuid4()), created_by=cu.id, **dados)
    db.add(c)
    await db.flush()
    approval_info = None
    if approval_required:
        approval_info = await solicitar_ou_consumir_aprovacao(
            db,
            entity_type="case_expense",
            entity_id=c.id,
            amount=req.valor,
            user=cu,
            reason="Pagamento de despesa do caso acima da alçada configurada.",
        )
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "CREATE",
        "centro_custos",
        c.id,
        dados_depois={
            "case_id": req.case_id,
            "tipo": req.tipo.value,
            "categoria": req.categoria.value,
            "valor": str(_money(req.valor)),
            "moeda": req.moeda,
            "pago": req.pago,
            "comprovante_id": req.comprovante_id,
        },
    )
    await db.commit()
    out = _out(c)
    if approval_info and approval_info.get("required"):
        out["approval_required"] = True
        out["approval_id"] = approval_info.get("approval_id")
        out["approval_threshold"] = float(approval_info.get("threshold") or 0)
    return out


def _totais_centro_custo():
    return (
        func.coalesce(func.sum(sa_case((CentroCusto.tipo == CentroCustoTipo.receita, CentroCusto.valor), else_=0)), 0).label('total_receitas'),
        func.coalesce(func.sum(sa_case((CentroCusto.tipo == CentroCustoTipo.despesa, CentroCusto.valor), else_=0)), 0).label('total_despesas'),
        func.coalesce(func.sum(sa_case(((CentroCusto.tipo == CentroCustoTipo.despesa) & CentroCusto.pago.is_(False), CentroCusto.valor), else_=0)), 0).label('pendente_pagar'),
    )

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
            *_totais_centro_custo(),
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
            *_totais_centro_custo(),
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
    competencia_atual = competencia_de_data(
        c.data_pagamento if c.pago else c.data_lancamento
    )
    await exigir_competencia_aberta(
        db, competencia_atual, "Alterar centro de custos"
    )
    dados = req.model_dump(exclude_none=True)
    data_ref = dados.get("data_pagamento") or c.data_pagamento or c.data_lancamento
    await exigir_competencia_aberta(
        db, competencia_de_data(data_ref), "Alterar centro de custos"
    )
    if dados.get("pago") is True and not c.pago:
        approval = await solicitar_ou_consumir_aprovacao(
            db,
            entity_type="case_expense",
            entity_id=c.id,
            amount=c.valor,
            user=cu,
            reason="Pagamento de despesa do caso acima da alçada configurada.",
        )
        if approval.get("required"):
            await db.commit()
            out = _out(c)
            out["approval_required"] = True
            out["approval_id"] = approval.get("approval_id")
            out["approval_threshold"] = float(approval.get("threshold") or 0)
            return out
    for campo, valor in dados.items():
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
    await exigir_competencia_aberta(
        db,
        competencia_de_data(c.data_pagamento if c.pago else c.data_lancamento),
        "Excluir centro de custos",
    )
    # Soft-delete (arquitetural): nunca apagar lançamento financeiro fisicamente
    c.deleted_at = datetime.now(timezone.utc)
    await criar_audit_log(
        db, cu.id, cu.role.value, "DELETE", "centro_custos", lancamento_id,
        detalhes=f"Lançamento {c.tipo} de {float(c.valor):.2f} {c.moeda} no caso {c.case_id}",
    )
    await db.commit()
