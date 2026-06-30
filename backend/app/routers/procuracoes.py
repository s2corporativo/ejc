# ── app/routers/procuracoes.py ───────────────────────────────────────────────
from __future__ import annotations
from datetime import datetime, timezone, date
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.procuracao import Procuracao
from app.models.audit_log import criar_audit_log
from app.schemas.procuracao import ProcuracaoCreate, ProcuracaoResponse
from app.schemas.common import MsgResponse

router = APIRouter(prefix="/procuracoes", tags=["Procurações"])

_ADV = {"superadmin", "admin", "socio", "advogado", "advogado_auxiliar"}


def _req_adv(cu: User = Depends(get_current_user)) -> User:
    # Emissão/revogação de procuração = ato jurídico: só equipe jurídica (advogado+).
    if cu.role.value not in _ADV:
        raise HTTPException(status_code=403, detail="Acesso restrito à equipe jurídica")
    return cu


@router.get("/")
async def listar(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    client_id: Optional[str] = None,
    vencendo: bool = False,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(Procuracao).where(
        Procuracao.deleted_at.is_(None), Procuracao.revogada == False,
    )
    if client_id:
        q = q.where(Procuracao.client_id == client_id)
    if vencendo:
        from datetime import timedelta
        q = q.where(
            Procuracao.data_validade.isnot(None),
            Procuracao.data_validade <= date.today() + timedelta(days=30),
        )
    q = q.order_by(Procuracao.data_validade.asc().nullslast())

    total = (await db.execute(
        select(sqlfunc.count()).select_from(q.subquery())
    )).scalar()
    rows = (await db.execute(
        q.offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {
        "data": [ProcuracaoResponse.model_validate(p) for p in rows],
        "total": total, "page": page, "page_size": page_size,
    }


@router.post("/", response_model=ProcuracaoResponse, status_code=201)
async def criar(
    payload: ProcuracaoCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_adv),
):
    p = Procuracao(id=str(uuid4()), **payload.model_dump())
    db.add(p)
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "procuracoes", p.id)
    await db.commit()
    await db.refresh(p)
    return p


@router.post("/{proc_id}/revogar", response_model=MsgResponse)
async def revogar(
    proc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_adv),
):
    p = (await db.execute(
        select(Procuracao).where(
            Procuracao.id == proc_id, Procuracao.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Procuração não encontrada")
    p.revogada = True
    p.revogada_em = date.today()
    await criar_audit_log(db, cu.id, cu.role.value, "REVOGACAO", "procuracoes", proc_id)
    await db.commit()
    return MsgResponse(detail="Procuração revogada")
