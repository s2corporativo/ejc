"""Despesas processuais por caso.

Lançamento = sub-recurso jurídico do caso, sujeito ao ownership canônico.
Faturamento = consolidação explícita em `FeeTipo.custas_despesas`.

Não confundir com `/despesas`: aquele módulo representa overhead do escritório.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.case_despesa import CaseDespesa
from app.models.fee import Fee, FeeStatus, FeeTipo
from app.models.user import User
from app.schemas.common import MsgResponse

router = APIRouter(prefix="/despesas-processuais", tags=["Despesas Processuais"])

_FATURAR_ROLES = {"superadmin", "admin", "socio", "advogado", "financeiro"}
_CATEGORIAS = {
    "custas",
    "diligencia",
    "copias",
    "deslocamento",
    "pericia",
    "correios",
    "outro",
}


def _role(cu: User) -> str:
    value = getattr(cu, "role", "")
    return value.value if hasattr(value, "value") else str(value)


def _req_faturar(cu: User = Depends(get_current_user)) -> User:
    if _role(cu) not in _FATURAR_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito a advogado, gestão ou financeiro",
        )
    return cu


class DespesaIn(BaseModel):
    case_id: str = Field(min_length=1, max_length=36)
    data: date
    valor: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    descricao: str = Field(min_length=3, max_length=500)
    categoria: str = "outro"

    @field_validator("categoria")
    @classmethod
    def _categoria_valida(cls, value: str) -> str:
        if value not in _CATEGORIAS:
            raise ValueError(f"Categoria inválida; use uma de: {sorted(_CATEGORIAS)}")
        return value


class FaturarIn(BaseModel):
    data_vencimento: Optional[date] = None


async def _caso_para_faturamento(
    db: AsyncSession,
    cu: User,
    case_id: str,
) -> Case:
    """Financeiro pode faturar; demais papéis continuam sob ownership do caso."""
    if _role(cu) != "financeiro":
        return await verificar_acesso_caso(db, cu, case_id)
    case = (
        await db.execute(
            select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Caso não encontrado")
    return case


@router.get("/casos/{case_id}")
async def por_caso(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    await verificar_acesso_caso(db, cu, case_id)
    rows = (
        await db.execute(
            select(CaseDespesa)
            .where(
                CaseDespesa.case_id == case_id,
                CaseDespesa.deleted_at.is_(None),
            )
            .order_by(CaseDespesa.data.desc(), CaseDespesa.created_at.desc())
        )
    ).scalars().all()
    total = sum((r.valor for r in rows), Decimal("0"))
    pendente = sum((r.valor for r in rows if not r.fee_id), Decimal("0"))
    return {
        "data": [
            {
                "id": r.id,
                "data": r.data,
                "valor": r.valor,
                "descricao": r.descricao,
                "categoria": r.categoria,
                "faturada": bool(r.fee_id),
                "fee_id": r.fee_id,
                "user_id": r.user_id,
                "created_at": r.created_at,
            }
            for r in rows
        ],
        "total": total,
        "pendente_de_faturar": pendente,
    }


@router.post(
    "/",
    status_code=201,
    dependencies=[Depends(rate_limit("case-expense-create", 30))],
)
async def lancar(
    payload: DespesaIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    case = await verificar_acesso_caso(db, cu, payload.case_id)
    entry = CaseDespesa(
        id=str(uuid4()),
        case_id=payload.case_id,
        user_id=cu.id,
        data=payload.data,
        valor=payload.valor.quantize(Decimal("0.01")),
        descricao=payload.descricao.strip(),
        categoria=payload.categoria,
    )
    db.add(entry)
    await criar_audit_log(
        db,
        cu.id,
        _role(cu),
        "CREATE",
        "case_despesas",
        entry.id,
        dados_depois={
            "case_id": case.id,
            "valor": str(entry.valor),
            "categoria": entry.categoria,
            "data": str(entry.data),
        },
    )
    await db.commit()
    return {"id": entry.id, "detail": "Despesa processual lançada"}


@router.post(
    "/caso/{case_id}/faturar",
    status_code=201,
    dependencies=[Depends(rate_limit("case-expense-bill", 10))],
)
async def faturar(
    case_id: str,
    payload: FaturarIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_faturar),
):
    """Consolida, de modo concorrente-seguro, despesas ainda não faturadas."""
    case = await _caso_para_faturamento(db, cu, case_id)

    # Serializa dois faturamentos simultâneos do mesmo caso. O lock é
    # transacional e desaparece no commit/rollback.
    await db.execute(
        select(Case.id).where(Case.id == case_id).with_for_update()
    )
    entries = (
        await db.execute(
            select(CaseDespesa)
            .where(
                CaseDespesa.case_id == case_id,
                CaseDespesa.deleted_at.is_(None),
                CaseDespesa.fee_id.is_(None),
            )
            .order_by(CaseDespesa.created_at)
            .with_for_update()
        )
    ).scalars().all()
    if not entries:
        raise HTTPException(
            status_code=422,
            detail="Sem despesas pendentes de faturamento",
        )

    valor_total = sum((entry.valor for entry in entries), Decimal("0"))
    fee = Fee(
        id=str(uuid4()),
        tipo=FeeTipo.custas_despesas,
        status=FeeStatus.pendente,
        descricao=(
            f"Reembolso de despesas processuais — {len(entries)} lançamento(s)"
        ),
        valor=valor_total,
        data_vencimento=payload.data_vencimento,
        case_id=case_id,
        client_id=case.client_id,
    )
    db.add(fee)
    await db.flush()
    ids = []
    for entry in entries:
        entry.fee_id = fee.id
        ids.append(entry.id)

    await criar_audit_log(
        db,
        cu.id,
        _role(cu),
        "CREATE",
        "fees",
        fee.id,
        detalhes=(
            f"Faturamento de {len(entries)} despesa(s) processual(is) — "
            f"R$ {valor_total:.2f}"
        ),
        dados_depois={
            "case_id": case_id,
            "case_despesas": ids,
            "tipo": FeeTipo.custas_despesas.value,
            "valor": str(valor_total),
        },
    )
    await db.commit()
    return {
        "fee_id": fee.id,
        "valor": float(valor_total),
        "lancamentos": len(entries),
        "detail": "Honorário de despesas gerado",
    }


@router.delete("/{entry_id}", response_model=MsgResponse)
async def remover(
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    entry = (
        await db.execute(
            select(CaseDespesa).where(
                CaseDespesa.id == entry_id,
                CaseDespesa.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")
    await verificar_acesso_caso(db, cu, entry.case_id)
    if entry.fee_id:
        raise HTTPException(
            status_code=422,
            detail="Despesa já faturada — cancele o honorário antes",
        )

    entry.deleted_at = datetime.now(timezone.utc)
    await criar_audit_log(
        db,
        cu.id,
        _role(cu),
        "DELETE",
        "case_despesas",
        entry.id,
        dados_antes={
            "case_id": entry.case_id,
            "valor": str(entry.valor),
            "categoria": entry.categoria,
            "data": str(entry.data),
        },
    )
    await db.commit()
    return MsgResponse(detail="Despesa processual removida")
