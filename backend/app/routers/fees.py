# ── app/routers/fees.py ──────────────────────────────────────────────────────
# Honorários, custas/despesas e pagamentos parciais.
from __future__ import annotations

import re
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
from app.services.document_access_policy import exigir_documento_compativel_com_caso
from app.services.fee_ledger_compat import total_pago_efetivo

_FINANCEIRO_TOTAL = {"superadmin", "admin", "socio", "financeiro"}
_RE_COMPETENCIA = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


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


async def _total_pago_fee(db: AsyncSession, fee_id: str) -> Decimal:
    fee = (
        await db.execute(
            select(Fee).where(Fee.id == fee_id, Fee.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if fee is None:
        return Decimal("0")
    total, _legado = await total_pago_efetivo(db, fee)
    return total


async def _fee_visivel(db: AsyncSession, fee_id: str, user: User) -> Optional[Fee]:
    q = select(Fee).where(Fee.id == fee_id, Fee.deleted_at.is_(None))
    q = _filtro_fees_lista(q, user)
    return (await db.execute(q)).scalar_one_or_none()


router = APIRouter(prefix="/fees", tags=["Honorários"])


@router.get("/")
async def listar(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_f: Optional[str] = Query(None, alias="status"),
    client_id: Optional[str] = None,
    case_id: Optional[str] = None,
    competencia: Optional[str] = Query(
        None, description="Filtra pelo mês de vencimento (formato AAAA-MM)"
    ),
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
    if competencia:
        if not _RE_COMPETENCIA.fullmatch(competencia):
            raise HTTPException(
                status_code=422,
                detail="competencia inválida: use o formato AAAA-MM",
            )
        ano, mes = competencia.split("-")
        q = q.where(
            sqlfunc.extract("year", Fee.data_vencimento) == int(ano),
            sqlfunc.extract("month", Fee.data_vencimento) == int(mes),
        )
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
    """KPIs de cobrança/caixa com compatibilidade para quitações legadas.

    O subledger ganha sempre. Um fee legado ``pago`` só entra no caixa quando
    não existe nenhum ``fee_payments`` para ele, evitando dupla contagem.
    """
    hoje = date.today()

    pagamentos_por_fee = (
        select(
            FeePayment.fee_id.label("fee_id"),
            sqlfunc.coalesce(sqlfunc.sum(FeePayment.valor), 0).label("total_pago"),
        )
        .group_by(FeePayment.fee_id)
        .subquery()
    )
    total_pago = sqlfunc.coalesce(pagamentos_por_fee.c.total_pago, 0)
    saldo = sqlfunc.greatest(sqlfunc.coalesce(Fee.valor, 0) - total_pago, 0)

    base_saldos = (
        select(
            sqlfunc.coalesce(sqlfunc.sum(saldo).filter(Fee.status == FeeStatus.pendente), 0),
            sqlfunc.coalesce(sqlfunc.sum(saldo).filter(Fee.status == FeeStatus.atrasado), 0),
        )
        .outerjoin(pagamentos_por_fee, pagamentos_por_fee.c.fee_id == Fee.id)
        .where(Fee.deleted_at.is_(None))
    )
    base_caixa = (
        select(sqlfunc.coalesce(sqlfunc.sum(FeePayment.valor), 0))
        .join(Fee, Fee.id == FeePayment.fee_id)
        .where(
            Fee.deleted_at.is_(None),
            sqlfunc.extract("month", FeePayment.data_pagamento) == hoje.month,
            sqlfunc.extract("year", FeePayment.data_pagamento) == hoje.year,
        )
    )
    existe_pagamento = select(FeePayment.id).where(FeePayment.fee_id == Fee.id).exists()
    base_caixa_legado = select(sqlfunc.coalesce(sqlfunc.sum(Fee.valor), 0)).where(
        Fee.deleted_at.is_(None),
        Fee.status == FeeStatus.pago,
        Fee.valor.is_not(None),
        Fee.data_pagamento.is_not(None),
        sqlfunc.extract("month", Fee.data_pagamento) == hoje.month,
        sqlfunc.extract("year", Fee.data_pagamento) == hoje.year,
        ~existe_pagamento,
    )
    base_percentuais = select(sqlfunc.count(Fee.id)).where(
        Fee.deleted_at.is_(None),
        Fee.valor.is_(None),
        Fee.percentual_exito.is_not(None),
        Fee.status.in_([FeeStatus.pendente, FeeStatus.atrasado]),
    )

    escopo = "escritorio"
    if not _ve_financeiro_total(cu):
        ids = _ids_casos_do_usuario(cu)
        base_saldos = base_saldos.where(Fee.case_id.in_(ids))
        base_caixa = base_caixa.where(Fee.case_id.in_(ids))
        base_caixa_legado = base_caixa_legado.where(Fee.case_id.in_(ids))
        base_percentuais = base_percentuais.where(Fee.case_id.in_(ids))
        escopo = "meus_casos"

    pendente, atrasado = (await db.execute(base_saldos)).one()
    recebido_real = Decimal(str((await db.execute(base_caixa)).scalar() or 0))
    recebido_legado = Decimal(str((await db.execute(base_caixa_legado)).scalar() or 0))
    percentuais_sem_valor = (await db.execute(base_percentuais)).scalar() or 0
    return {
        "pendente": float(pendente or 0),
        "atrasado": float(atrasado or 0),
        "recebido_mes": float(recebido_real + recebido_legado),
        "recebido_mes_legado": float(recebido_legado),
        "percentuais_sem_valor": int(percentuais_sem_valor),
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
        if caso.client_id != payload.client_id:
            raise HTTPException(
                status_code=422,
                detail="client_id não corresponde ao cliente do caso informado",
            )

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

    alteracoes = payload.model_dump(exclude_unset=True)
    total_pago, _legado = await total_pago_efetivo(db, fee)
    novo_valor = alteracoes.get("valor", fee.valor)
    novo_status = alteracoes.get("status", fee.status)
    novo_status_valor = getattr(novo_status, "value", novo_status)

    if novo_valor is not None and Decimal(str(novo_valor)) < total_pago:
        raise HTTPException(
            status_code=422,
            detail=(
                "valor do honorário não pode ficar abaixo do total já recebido; "
                "registre eventual estorno em fluxo próprio antes de reduzir a cobrança"
            ),
        )
    if novo_status_valor == FeeStatus.cancelado.value and total_pago > 0:
        raise HTTPException(
            status_code=409,
            detail="honorário com pagamento não pode ser cancelado sem conciliação/estorno",
        )
    if novo_status_valor == FeeStatus.pago.value:
        if novo_valor is None:
            raise HTTPException(
                status_code=422,
                detail="honorário percentual sem valor monetário realizado não pode ser quitado manualmente",
            )
        if total_pago < Decimal(str(novo_valor)):
            raise HTTPException(
                status_code=422,
                detail="status 'pago' exige pagamentos registrados que cubram o valor do honorário",
            )

    dados_antes = jsonable_encoder(
        {key: getattr(fee, key, None) for key in alteracoes}
    )
    for key, value in alteracoes.items():
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


@router.get("/{fee_id}/pagamentos")
async def listar_pagamentos(
    fee_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Subledger de recebimentos, com fallback explícito para quitação legada."""
    fee = await _fee_visivel(db, fee_id, cu)
    if not fee:
        raise HTTPException(status_code=404, detail="Honorário não encontrado")

    pagamentos = (
        await db.execute(
            select(FeePayment)
            .where(FeePayment.fee_id == fee_id)
            .order_by(FeePayment.data_pagamento.desc(), FeePayment.created_at.desc())
        )
    ).scalars().all()
    total_pago, legado = await total_pago_efetivo(db, fee)
    saldo = None
    if fee.valor is not None:
        saldo = max(Decimal(str(fee.valor)) - total_pago, Decimal("0"))

    return {
        "fee_id": fee_id,
        "valor_contratado": float(fee.valor) if fee.valor is not None else None,
        "percentual_exito": (
            float(fee.percentual_exito) if fee.percentual_exito is not None else None
        ),
        "total_pago": float(total_pago),
        "saldo": float(saldo) if saldo is not None else None,
        "legacy_pago_sem_subledger": legado,
        "data_pagamento_legacy": (
            fee.data_pagamento.isoformat() if legado and fee.data_pagamento else None
        ),
        "pagamentos": [
            {
                "id": p.id,
                "valor": float(p.valor),
                "data_pagamento": p.data_pagamento.isoformat(),
                "forma": p.forma,
                "comprovante_doc_id": p.comprovante_doc_id,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in pagamentos
        ],
    }


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
    if fee.status == FeeStatus.cancelado:
        raise HTTPException(status_code=409, detail="Honorário cancelado não aceita pagamento")
    if fee.status == FeeStatus.pago:
        raise HTTPException(status_code=409, detail="Honorário já está quitado")

    if payload.comprovante_doc_id:
        if not fee.case_id:
            raise HTTPException(
                status_code=422,
                detail="comprovante documental só pode ser vinculado a honorário associado a um caso",
            )
        caso = (
            await db.execute(
                select(Case).where(
                    Case.id == fee.case_id,
                    Case.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not caso:
            raise HTTPException(status_code=409, detail="Caso do honorário não está disponível")
        await exigir_documento_compativel_com_caso(
            db,
            cu,
            document_id=payload.comprovante_doc_id,
            case=caso,
        )

    total_antes, legado = await total_pago_efetivo(db, fee)
    if legado:
        raise HTTPException(
            status_code=409,
            detail=(
                "Honorário quitado em registro legado sem subledger; normalize o histórico "
                "em fluxo controlado antes de lançar novo pagamento"
            ),
        )
    if fee.valor is not None:
        devido = Decimal(str(fee.valor))
        if total_antes >= devido:
            raise HTTPException(
                status_code=409,
                detail="O valor do honorário já está integralmente coberto pelos pagamentos existentes",
            )
        if total_antes + payload.valor > devido:
            raise HTTPException(
                status_code=422,
                detail="Pagamento excede o saldo do honorário; concilie crédito/estorno em fluxo próprio",
            )

    payment = FeePayment(
        id=str(uuid4()),
        fee_id=fee_id,
        valor=payload.valor,
        data_pagamento=payload.data_pagamento,
        forma=payload.forma,
        comprovante_doc_id=payload.comprovante_doc_id,
    )
    db.add(payment)
    await db.flush()

    total_pago, _legado_pos = await total_pago_efetivo(db, fee)

    quitado = False
    quitacao_indeterminada = fee.valor is None and fee.percentual_exito is not None
    if fee.valor is not None and total_pago >= Decimal(str(fee.valor)):
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
        detalhes=(
            f"Pagamento {payment.id} registrado; quitado={quitado}; "
            f"quitacao_indeterminada={quitacao_indeterminada}"
        ),
        dados_depois={
            "payment_id": payment.id,
            "forma": payment.forma,
            "comprovante_vinculado": bool(payment.comprovante_doc_id),
            "quitado": quitado,
            "quitacao_indeterminada": quitacao_indeterminada,
        },
    )
    await db.commit()
    return {
        "id": payment.id,
        "total_pago": float(total_pago),
        "quitado": quitado,
        "quitacao_indeterminada": quitacao_indeterminada,
        "detail": (
            "Pagamento registrado; quitação percentual depende de base de cálculo monetária"
            if quitacao_indeterminada
            else "Pagamento registrado"
        ),
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

    total_pago, _legado = await total_pago_efetivo(db, fee)
    if total_pago > 0:
        raise HTTPException(
            status_code=409,
            detail="Honorário com pagamento não pode ser cancelado sem conciliação/estorno",
        )

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