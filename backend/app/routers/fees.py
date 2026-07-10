# ── app/routers/fees.py ──────────────────────────────────────────────────────
# Honorários, custas/despesas e pagamentos parciais.
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func as sqlfunc
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.fee import Fee, FeePayment, FeeStatus
from app.models.user import User
from app.schemas.common import MsgResponse
from app.schemas.fee import FeeCreate, FeePaymentCreate, FeeResponse, FeeUpdate

_FINANCEIRO_TOTAL = {"superadmin", "admin", "socio", "financeiro"}


def _ve_financeiro_total(user: User) -> bool:
    """Gestão, sócios e financeiro enxergam o consolidado institucional."""
    return user.role.value in _FINANCEIRO_TOTAL


def _req_financeiro_mutacao(cu: User = Depends(get_current_user)) -> User:
    """Mutações financeiras são reservadas a perfis fiduciários definidos."""
    if cu.role.value not in _FINANCEIRO_TOTAL:
        raise HTTPException(
            status_code=403,
            detail="Sem permissão para alterar dados financeiros",
        )
    return cu


def _ids_casos_do_usuario(user: User):
    """IDs dos casos em que o usuário atua como responsável ou auxiliar."""
    return (
        select(Case.id)
        .where(
            Case.deleted_at.is_(None),
            or_(
                Case.advogado_responsavel_id == user.id,
                Case.advogado_auxiliar_id == user.id,
            ),
        )
        .scalar_subquery()
    )


def _filtro_fees_lista(q, user: User):
    """Perfis fiduciários veem tudo; advogados veem apenas honorários dos casos próprios."""
    if _ve_financeiro_total(user):
        return q
    return q.where(Fee.case_id.in_(_ids_casos_do_usuario(user)))


router = APIRouter(prefix="/fees", tags=["Honorários"])


@router.get("/")
async def listar(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_f: Optional[str] = Query(None, alias="status"),
    client_id: Optional[str] = None,
    case_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(Fee).where(Fee.deleted_at.is_(None))
    q = _filtro_fees_lista(q, cu)
    if status_f:
        q = q.where(Fee.status == status_f)
    if client_id:
        q = q.where(Fee.client_id == client_id)
    if case_id:
        q = q.where(Fee.case_id == case_id)
    q = q.order_by(Fee.data_vencimento.asc().nullslast())

    total = (
        await db.execute(select(sqlfunc.count()).select_from(q.subquery()))
    ).scalar()
    rows = (
        await db.execute(q.offset((page - 1) * page_size).limit(page_size))
    ).scalars().all()
    return {
        "data": [FeeResponse.model_validate(f) for f in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/resumo")
async def resumo(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """KPIs institucionais para perfis fiduciários; demais veem apenas seus casos."""
    hoje = date.today()
    base = select(
        sqlfunc.sum(Fee.valor).filter(Fee.status == FeeStatus.pendente),
        sqlfunc.sum(Fee.valor).filter(Fee.status == FeeStatus.atrasado),
        sqlfunc.sum(Fee.valor).filter(
            Fee.status == FeeStatus.pago,
            sqlfunc.extract("month", Fee.data_pagamento) == hoje.month,
            sqlfunc.extract("year", Fee.data_pagamento) == hoje.year,
        ),
    ).where(Fee.deleted_at.is_(None))

    escopo = "escritorio"
    if not _ve_financeiro_total(cu):
        base = base.where(Fee.case_id.in_(_ids_casos_do_usuario(cu)))
        escopo = "meus_casos"

    pendente, atrasado, recebido_mes = (await db.execute(base)).one()
    return {
        "pendente": float(pendente or 0),
        "atrasado": float(atrasado or 0),
        "recebido_mes": float(recebido_mes or 0),
        "escopo": escopo,
    }


@router.post("/", response_model=FeeResponse, status_code=201)
async def criar(
    payload: FeeCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_financeiro_mutacao),
):
    if payload.case_id:
        caso = (
            await db.execute(
                select(Case).where(
                    Case.id == payload.case_id,
                    Case.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not caso:
            raise HTTPException(status_code=404, detail="Caso não encontrado")

    fee = Fee(id=str(uuid4()), **payload.model_dump())
    db.add(fee)
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "CREATE",
        "fees",
        fee.id,
        detalhes="Honorário criado por perfil financeiro autorizado.",
    )
    await db.commit()
    await db.refresh(fee)
    return fee


@router.patch("/{fee_id}", response_model=FeeResponse)
async def atualizar(
    fee_id: str,
    payload: FeeUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_financeiro_mutacao),
):
    fee = (
        await db.execute(
            select(Fee).where(Fee.id == fee_id, Fee.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if not fee:
        raise HTTPException(status_code=404, detail="Honorário não encontrado")

    dados_antes = jsonable_encoder(
        {
            key: getattr(fee, key, None)
            for key in payload.model_dump(exclude_unset=True)
        }
    )
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(fee, key, value)

    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "UPDATE",
        "fees",
        fee_id,
        dados_antes=dados_antes,
        dados_depois=payload.model_dump(exclude_unset=True, mode="json"),
    )
    await db.commit()
    await db.refresh(fee)
    return fee


@router.post("/{fee_id}/pagamentos", status_code=201)
async def registrar_pagamento(
    fee_id: str,
    payload: FeePaymentCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_financeiro_mutacao),
):
    """Registra pagamento parcial e quita quando a soma alcança o valor contratado."""
    fee = (
        await db.execute(
            select(Fee).where(Fee.id == fee_id, Fee.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if not fee:
        raise HTTPException(status_code=404, detail="Honorário não encontrado")

    payment = FeePayment(
        id=str(uuid4()),
        fee_id=fee_id,
        valor=payload.valor,
        data_pagamento=payload.data_pagamento,
        forma=payload.forma,
    )
    db.add(payment)
    await db.flush()

    total_pago = (
        await db.execute(
            select(sqlfunc.coalesce(sqlfunc.sum(FeePayment.valor), 0)).where(
                FeePayment.fee_id == fee_id
            )
        )
    ).scalar()

    quitado = False
    if fee.valor and Decimal(total_pago) >= fee.valor:
        fee.status = FeeStatus.pago
        fee.data_pagamento = payload.data_pagamento
        quitado = True

    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "PAGAMENTO",
        "fees",
        fee_id,
        detalhes=f"Pagamento registrado; quitado={quitado}",
    )
    await db.commit()
    return {
        "id": payment.id,
        "total_pago": float(total_pago),
        "quitado": quitado,
        "detail": "Pagamento registrado",
    }


@router.delete("/{fee_id}", response_model=MsgResponse)
async def cancelar(
    fee_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_financeiro_mutacao),
):
    fee = (
        await db.execute(
            select(Fee).where(Fee.id == fee_id, Fee.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if not fee:
        raise HTTPException(status_code=404, detail="Honorário não encontrado")

    fee.deleted_at = datetime.now(timezone.utc)
    fee.status = FeeStatus.cancelado
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "DELETE",
        "fees",
        fee_id,
        detalhes="Honorário cancelado por perfil financeiro autorizado.",
    )
    await db.commit()
    return MsgResponse(detail="Honorário cancelado")
