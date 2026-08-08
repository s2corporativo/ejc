# ── app/routers/despesas_processuais.py ──────────────────────────────────────
"""Despesa processual por caso (F3.2 / Issue #806) — mesmo desenho de
timesheet.py: lançamento cru (qualquer um com acesso ao caso) + consolidação
explícita em Fee (`custas_despesas`, restrita a advogado/gestão/financeiro).

Não confundir com /despesas (despesas.py) — aquele é overhead do escritório
(SQL bruto, RBAC restrito a superadmin/admin/socio/financeiro). Esta é a
despesa do PROCESSO, lançada por quem trabalha o caso, existente para ser
reembolsada pelo cliente.
"""
from __future__ import annotations
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ownership import verificar_acesso_caso
from app.models.user import User
from app.models.case import Case
from app.models.case_despesa import CaseDespesa
from app.models.fee import Fee, FeeTipo, FeeStatus
from app.models.audit_log import criar_audit_log
from app.schemas.common import MsgResponse

router = APIRouter(prefix="/despesas-processuais", tags=["Despesas Processuais"])

# Mesmo conjunto de papéis de timesheet.py::_FAT — consolidar em Fee é ato
# de faturamento, não de lançar a despesa em si.
_FAT = {"superadmin", "admin", "socio", "advogado", "financeiro"}

CATEGORIAS = {
    "custas", "diligencia", "copias", "deslocamento", "pericia",
    "correios", "outro",
}


def _req_fat(cu: User = Depends(get_current_user)) -> User:
    if cu.role.value not in _FAT:
        raise HTTPException(status_code=403, detail="Acesso restrito a advogado/gestão/financeiro")
    return cu


class DespesaIn(BaseModel):
    case_id: str
    data: date
    valor: float = Field(gt=0)
    descricao: str = Field(min_length=3, max_length=500)
    categoria: str = "outro"

    @field_validator("categoria")
    @classmethod
    def _categoria_valida(cls, v: str) -> str:
        if v not in CATEGORIAS:
            raise ValueError(f"Categoria inválida; use uma de: {sorted(CATEGORIAS)}")
        return v


class FaturarIn(BaseModel):
    data_vencimento: Optional[date] = None


@router.get("/casos/{case_id}")
async def por_caso(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    await verificar_acesso_caso(db, cu, case_id)
    rows = (await db.execute(
        select(CaseDespesa).where(
            CaseDespesa.case_id == case_id, CaseDespesa.deleted_at.is_(None)
        ).order_by(CaseDespesa.data.desc())
    )).scalars().all()
    total = sum((r.valor for r in rows), Decimal("0"))
    pendente = sum((r.valor for r in rows if not r.fee_id), Decimal("0"))
    return {
        "data": [
            {"id": r.id, "data": r.data, "valor": r.valor,
             "descricao": r.descricao, "categoria": r.categoria,
             "faturada": bool(r.fee_id), "user_id": r.user_id}
            for r in rows
        ],
        "total": total,
        "pendente_de_faturar": pendente,
    }


@router.post("/", status_code=201)
async def lancar(
    payload: DespesaIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    case = (await db.execute(select(Case).where(
        Case.id == payload.case_id, Case.deleted_at.is_(None)
    ))).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=422, detail="Caso não encontrado")
    await verificar_acesso_caso(db, cu, payload.case_id)
    dados = payload.model_dump()
    dados["valor"] = Decimal(str(dados["valor"])).quantize(Decimal("0.01"))
    e = CaseDespesa(id=str(uuid4()), user_id=cu.id, **dados)
    db.add(e)
    await db.commit()
    return {"id": e.id, "detail": "Despesa lançada"}


@router.post("/caso/{case_id}/faturar", status_code=201)
async def faturar(
    case_id: str, payload: FaturarIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_fat),
):
    """Consolida despesas pendentes em UM honorário custas_despesas."""
    case = (await db.execute(select(Case).where(
        Case.id == case_id, Case.deleted_at.is_(None)
    ))).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=422, detail="Caso não encontrado")
    await verificar_acesso_caso(db, cu, case_id)

    entries = (await db.execute(
        select(CaseDespesa).where(
            CaseDespesa.case_id == case_id,
            CaseDespesa.deleted_at.is_(None),
            CaseDespesa.fee_id.is_(None),
        )
    )).scalars().all()
    if not entries:
        raise HTTPException(status_code=422, detail="Sem despesas pendentes de faturamento")

    valor_total = sum((e.valor for e in entries), Decimal("0"))

    fee = Fee(
        id=str(uuid4()), tipo=FeeTipo.custas_despesas, status=FeeStatus.pendente,
        descricao=f"Reembolso de despesas processuais — {len(entries)} lançamento(s)",
        valor=valor_total, data_vencimento=payload.data_vencimento,
        case_id=case_id, client_id=case.client_id,
    )
    db.add(fee)
    await db.flush()
    for e in entries:
        e.fee_id = fee.id

    await criar_audit_log(
        db, cu.id, cu.role.value, "CREATE", "fees", fee.id,
        detalhes=f"Faturamento de {len(entries)} despesa(s) processual(is) — R$ {valor_total:.2f}",
    )
    await db.commit()
    return {"fee_id": fee.id, "valor": float(valor_total),
            "lancamentos": len(entries), "detail": "Honorário de despesas gerado"}


@router.delete("/{entry_id}", response_model=MsgResponse)
async def remover(
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    e = (await db.execute(select(CaseDespesa).where(
        CaseDespesa.id == entry_id, CaseDespesa.deleted_at.is_(None)
    ))).scalar_one_or_none()
    if not e:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")
    await verificar_acesso_caso(db, cu, e.case_id)
    if e.fee_id:
        raise HTTPException(status_code=422, detail="Despesa já faturada — cancele o honorário antes")
    e.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return MsgResponse(detail="Despesa removida")
