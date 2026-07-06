# ── app/routers/timesheet.py ─────────────────────────────────────────────────
# Timesheet: registro de horas por caso + faturamento (gera Fee por_hora).
from __future__ import annotations
from datetime import datetime, timezone, date
from decimal import Decimal
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ownership import verificar_acesso_caso
from app.models.user import User
from app.models.time_entry import TimeEntry
from app.models.case import Case
from app.models.fee import Fee, FeeTipo, FeeStatus
from app.models.audit_log import criar_audit_log
from app.schemas.common import MsgResponse

router = APIRouter(prefix="/timesheet", tags=["Timesheet"])

_FAT = {"superadmin", "admin", "socio", "advogado", "financeiro"}


def _req_fat(cu: User = Depends(get_current_user)) -> User:
    # Faturar horas CRIA honorário (Fee): só advogado do caso / gestão / financeiro.
    if cu.role.value not in _FAT:
        raise HTTPException(status_code=403, detail="Acesso restrito a advogado/gestão/financeiro")
    return cu


class EntryIn(BaseModel):
    case_id: str
    data: date
    minutos: int = Field(gt=0, le=1440)
    descricao: str = Field(min_length=3, max_length=500)
    faturavel: bool = True


class FaturarIn(BaseModel):
    valor_hora: float = Field(gt=0)
    data_vencimento: Optional[date] = None


@router.get("/casos/{case_id}")
async def por_caso(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    await verificar_acesso_caso(db, cu, case_id)
    rows = (await db.execute(
        select(TimeEntry).where(
            TimeEntry.case_id == case_id, TimeEntry.deleted_at.is_(None)
        ).order_by(TimeEntry.data.desc())
    )).scalars().all()
    total_min = sum(r.minutos for r in rows)
    pendente_min = sum(r.minutos for r in rows if r.faturavel and not r.fee_id)
    return {
        "data": [
            {"id": r.id, "data": r.data, "minutos": r.minutos,
             "descricao": r.descricao, "faturavel": r.faturavel,
             "faturada": bool(r.fee_id), "user_id": r.user_id}
            for r in rows
        ],
        "total_horas": round(total_min / 60, 2),
        "horas_a_faturar": round(pendente_min / 60, 2),
    }


@router.post("/", status_code=201)
async def lancar(
    payload: EntryIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    case = (await db.execute(select(Case).where(
        Case.id == payload.case_id, Case.deleted_at.is_(None)
    ))).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=422, detail="Caso não encontrado")
    await verificar_acesso_caso(db, cu, payload.case_id)
    e = TimeEntry(id=str(uuid4()), user_id=cu.id, **payload.model_dump())
    db.add(e)
    await db.commit()
    return {"id": e.id, "detail": "Horas lançadas"}


@router.post("/caso/{case_id}/faturar", status_code=201)
async def faturar(
    case_id: str, payload: FaturarIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_fat),
):
    """Consolida horas faturáveis não-faturadas em UM honorário por_hora."""
    case = (await db.execute(select(Case).where(
        Case.id == case_id, Case.deleted_at.is_(None)
    ))).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=422, detail="Caso não encontrado")
    await verificar_acesso_caso(db, cu, case_id)

    entries = (await db.execute(
        select(TimeEntry).where(
            TimeEntry.case_id == case_id,
            TimeEntry.deleted_at.is_(None),
            TimeEntry.faturavel == True,
            TimeEntry.fee_id.is_(None),
        )
    )).scalars().all()
    if not entries:
        raise HTTPException(status_code=422, detail="Sem horas pendentes de faturamento")

    total_min = sum(e.minutos for e in entries)
    horas = Decimal(total_min) / Decimal(60)
    valor = (horas * Decimal(str(payload.valor_hora))).quantize(Decimal("0.01"))

    fee = Fee(
        id=str(uuid4()), tipo=FeeTipo.por_hora, status=FeeStatus.pendente,
        descricao=f"Honorários por hora — {float(horas):.2f}h × R$ {payload.valor_hora:.2f}",
        valor=valor, data_vencimento=payload.data_vencimento,
        case_id=case_id, client_id=case.client_id,
    )
    db.add(fee)
    await db.flush()
    for e in entries:
        e.fee_id = fee.id

    await criar_audit_log(
        db, cu.id, cu.role.value, "CREATE", "fees", fee.id,
        detalhes=f"Faturamento de {len(entries)} lançamento(s) — {float(horas):.2f}h",
    )
    await db.commit()
    return {"fee_id": fee.id, "horas": float(horas), "valor": float(valor),
            "lancamentos": len(entries), "detail": "Honorário gerado"}


@router.delete("/{entry_id}", response_model=MsgResponse)
async def remover(
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    e = (await db.execute(select(TimeEntry).where(
        TimeEntry.id == entry_id, TimeEntry.deleted_at.is_(None)
    ))).scalar_one_or_none()
    if not e:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")
    await verificar_acesso_caso(db, cu, e.case_id)
    if e.fee_id:
        raise HTTPException(status_code=422, detail="Lançamento já faturado — cancele o honorário antes")
    e.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return MsgResponse(detail="Lançamento removido")
