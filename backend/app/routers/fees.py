# ── app/routers/fees.py ──────────────────────────────────────────────────────
# Honorários, custas/despesas e pagamentos parciais.
from __future__ import annotations
from datetime import datetime, timezone, date
from uuid import uuid4
from typing import Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func as sqlfunc, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_roles, ROLE_LEVEL
from app.models.user import User
from app.models.fee import Fee, FeePayment, FeeStatus
from app.models.case import Case
from app.models.audit_log import criar_audit_log
from app.schemas.fee import FeeCreate, FeeUpdate, FeePaymentCreate, FeeResponse
from app.schemas.common import MsgResponse


# ── Controle de acesso financeiro por perfil ─────────────────────────────────
def _ve_financeiro_total(user: User) -> bool:
    """Apenas admin+ enxerga o consolidado financeiro do escritório."""
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["admin"]


def _ids_casos_do_usuario(user: User):
    """
    Subquery com os IDs de casos em que o usuário atua (responsável OU auxiliar).
    Usada para escopar honorários ao advogado quando ele não vê tudo.
    """
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
    """
    Visibilidade da LISTA de honorários (operacional), espelhando a de casos:
    - admin/sócio: vê todos os honorários;
    - advogado/auxiliar: só os honorários vinculados aos seus casos.
    Honorários avulsos (case_id NULL) ficam restritos a admin/sócio.
    """
    if ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["socio"]:
        return q
    return q.where(Fee.case_id.in_(_ids_casos_do_usuario(user)))

router = APIRouter(prefix="/fees", tags=["Honorários"])


@router.get("/")
async def listar(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    status_f: Optional[str] = Query(None, alias="status"),
    client_id: Optional[str] = None,
    case_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(Fee).where(Fee.deleted_at.is_(None))
    q = _filtro_fees_lista(q, cu)   # advogado/auxiliar: só honorários dos seus casos
    if status_f:
        q = q.where(Fee.status == status_f)
    if client_id:
        q = q.where(Fee.client_id == client_id)
    if case_id:
        q = q.where(Fee.case_id == case_id)
    q = q.order_by(Fee.data_vencimento.asc().nullslast())

    total = (await db.execute(
        select(sqlfunc.count()).select_from(q.subquery())
    )).scalar()
    rows = (await db.execute(
        q.offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {
        "data": [FeeResponse.model_validate(f) for f in rows],
        "total": total, "page": page, "page_size": page_size,
    }


@router.get("/resumo")
async def resumo(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    KPIs financeiros.
    - admin+: consolidado de TODO o escritório;
    - demais (inclui sócio): apenas honorários dos casos em que o usuário atua.
    """
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
        # Consolidado do mês é exclusivo do admin: aqui mostramos só o que
        # o próprio usuário fatura (honorários dos casos onde ele atua).
        base = base.where(Fee.case_id.in_(_ids_casos_do_usuario(cu)))
        escopo = "meus_casos"

    r = await db.execute(base)
    pendente, atrasado, recebido_mes = r.one()
    return {
        "pendente": float(pendente or 0),
        "atrasado": float(atrasado or 0),
        "recebido_mes": float(recebido_mes or 0),
        "escopo": escopo,   # 'escritorio' (admin) | 'meus_casos' (demais)
    }


@router.post("/", response_model=FeeResponse, status_code=201)
async def criar(
    payload: FeeCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    # Verificar se o usuário tem acesso ao caso vinculado ao honorário
    if payload.case_id:
        caso = (await db.execute(
            select(Case).where(Case.id == payload.case_id, Case.deleted_at.is_(None))
        )).scalar_one_or_none()
        if not caso:
            raise HTTPException(status_code=404, detail="Caso não encontrado")
        if (cu.role.value not in ("superadmin", "admin", "socio")
                and caso.advogado_responsavel_id != cu.id
                and caso.advogado_auxiliar_id != cu.id):
            raise HTTPException(status_code=403,
                                detail="Sem permissão para lançar honorário neste caso")
    f = Fee(id=str(uuid4()), **payload.model_dump())
    db.add(f)
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "fees", f.id)
    await db.commit()
    await db.refresh(f)
    return f


@router.patch("/{fee_id}", response_model=FeeResponse)
async def atualizar(
    fee_id: str, payload: FeeUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    f = (await db.execute(
        select(Fee).where(Fee.id == fee_id, Fee.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not f:
        raise HTTPException(status_code=404, detail="Honorário não encontrado")
    # Verificar permissão sobre o caso vinculado ao honorário
    if f.case_id:
        caso = (await db.execute(
            select(Case).where(Case.id == f.case_id, Case.deleted_at.is_(None))
        )).scalar_one_or_none()
        if caso and (cu.role.value not in ("admin", "socio")
                     and caso.advogado_responsavel_id != cu.id
                     and caso.advogado_auxiliar_id != cu.id):
            raise HTTPException(status_code=403,
                                detail="Sem permissão para editar honorário deste caso")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(f, k, v)
    await criar_audit_log(db, cu.id, cu.role.value, "UPDATE", "fees", fee_id)
    await db.commit()
    await db.refresh(f)
    return f


@router.post("/{fee_id}/pagamentos", status_code=201)
async def registrar_pagamento(
    fee_id: str, payload: FeePaymentCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Pagamento parcial; quita automaticamente se soma >= valor."""
    f = (await db.execute(
        select(Fee).where(Fee.id == fee_id, Fee.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not f:
        raise HTTPException(status_code=404, detail="Honorário não encontrado")
    # Verificar permissão sobre o caso vinculado ao honorário (IDOR).
    if f.case_id:
        caso = (await db.execute(
            select(Case).where(Case.id == f.case_id, Case.deleted_at.is_(None))
        )).scalar_one_or_none()
        if caso and (cu.role.value not in ("admin", "socio")
                     and caso.advogado_responsavel_id != cu.id
                     and caso.advogado_auxiliar_id != cu.id):
            raise HTTPException(status_code=403,
                                detail="Sem permissão para registrar pagamento deste caso")

    p = FeePayment(
        id=str(uuid4()), fee_id=fee_id,
        valor=payload.valor, data_pagamento=payload.data_pagamento,
        forma=payload.forma,
    )
    db.add(p)
    await db.flush()

    # Soma pagamentos
    total_pago = (await db.execute(
        select(sqlfunc.coalesce(sqlfunc.sum(FeePayment.valor), 0))
        .where(FeePayment.fee_id == fee_id)
    )).scalar()

    quitado = False
    if f.valor and Decimal(total_pago) >= f.valor:
        f.status = FeeStatus.pago
        f.data_pagamento = payload.data_pagamento
        quitado = True

    await criar_audit_log(
        db, cu.id, cu.role.value, "PAGAMENTO", "fees", fee_id,
        detalhes=f"R$ {payload.valor} ({'quitado' if quitado else 'parcial'})",
    )
    await db.commit()
    return {
        "id": p.id, "total_pago": float(total_pago),
        "quitado": quitado, "detail": "Pagamento registrado",
    }


@router.delete("/{fee_id}", response_model=MsgResponse)
async def cancelar(
    fee_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["admin", "socio"])),
):
    f = (await db.execute(
        select(Fee).where(Fee.id == fee_id, Fee.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not f:
        raise HTTPException(status_code=404, detail="Honorário não encontrado")
    f.deleted_at = datetime.now(timezone.utc)
    f.status = FeeStatus.cancelado
    await criar_audit_log(db, cu.id, cu.role.value, "DELETE", "fees", fee_id)
    await db.commit()
    return MsgResponse(detail="Honorário cancelado")
