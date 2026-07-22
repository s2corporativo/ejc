# ── app/routers/case_next_actions.py ─────────────────────────────────────────
"""API canônica da próxima ação operacional do caso."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import is_gestao, verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import ROLE_LEVEL, get_current_user
from app.models.user import User
from app.schemas.case_next_action import (
    CaseNextActionComplete,
    CaseNextActionCreate,
    CaseNextActionWaiverCreate,
    CaseOperationalView,
)
from app.services import case_next_action as operations

router = APIRouter(
    prefix="/cases/{case_id}/proxima-acao",
    tags=["Próxima ação do caso"],
)


def _require_legal_operator(user: User) -> None:
    role = getattr(user.role, "value", user.role)
    if ROLE_LEVEL.get(role, 0) < ROLE_LEVEL["advogado_auxiliar"]:
        raise HTTPException(
            status_code=403,
            detail="Alteração da próxima ação restrita à equipe jurídica",
        )


@router.get("/responsaveis")
async def assignable_users(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista mínima de responsáveis permitidos, sem expor e-mail ou credenciais."""

    _require_legal_operator(current_user)
    case = await verificar_acesso_caso(db, current_user, case_id)
    query = select(User).where(
        User.deleted_at.is_(None),
        User.is_active.is_(True),
        User.role != "cliente_externo",
    )
    if not is_gestao(current_user):
        allowed_ids = {
            current_user.id,
            case.advogado_responsavel_id,
            case.advogado_auxiliar_id,
        }
        query = query.where(User.id.in_([item for item in allowed_ids if item]))

    users = (await db.execute(query.order_by(User.full_name))).scalars().all()
    return {
        "data": [
            {
                "id": user.id,
                "full_name": user.full_name,
                "role": getattr(user.role, "value", user.role),
            }
            for user in users
        ]
    }


@router.get("", response_model=CaseOperationalView)
async def view(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = await verificar_acesso_caso(db, current_user, case_id)
    return await operations.operational_view(db, case)


@router.put(
    "",
    response_model=CaseOperationalView,
    dependencies=[Depends(rate_limit("case-next-action-write", 30))],
)
async def set_action(
    case_id: str,
    payload: CaseNextActionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_legal_operator(current_user)
    case = await verificar_acesso_caso(db, current_user, case_id)
    return await operations.set_next_action(db, case, current_user, payload)


@router.post(
    "/concluir",
    response_model=CaseOperationalView,
    dependencies=[Depends(rate_limit("case-next-action-write", 30))],
)
async def complete_action(
    case_id: str,
    payload: CaseNextActionComplete,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_legal_operator(current_user)
    case = await verificar_acesso_caso(db, current_user, case_id)
    return await operations.complete_next_action(
        db,
        case,
        current_user,
        payload,
    )


@router.post(
    "/dispensar",
    response_model=CaseOperationalView,
    dependencies=[Depends(rate_limit("case-next-action-write", 20))],
)
async def waive_action(
    case_id: str,
    payload: CaseNextActionWaiverCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_legal_operator(current_user)
    case = await verificar_acesso_caso(db, current_user, case_id)
    return await operations.waive_next_action(
        db,
        case,
        current_user,
        payload,
    )
