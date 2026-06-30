# ── app/routers/users.py ─────────────────────────────────────────────────────
from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_admin, get_password_hash
from app.models.user import User
from app.models.audit_log import criar_audit_log
from app.schemas.auth import UserCreate, UserUpdate, UserResponse
from app.schemas.common import MsgResponse

router = APIRouter(prefix="/users", tags=["Usuários"])


@router.get("/")
async def listar(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_admin),
):
    q = select(User).where(User.deleted_at.is_(None)).order_by(User.full_name)
    total = (await db.execute(
        select(sqlfunc.count()).select_from(q.subquery())
    )).scalar()
    rows = (await db.execute(
        q.offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {
        "data": [UserResponse.model_validate(u) for u in rows],
        "total": total, "page": page, "page_size": page_size,
    }


@router.post("/", response_model=UserResponse, status_code=201)
async def criar(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_admin),
):
    exists = (await db.execute(
        select(User).where(User.email == payload.email.lower())
    )).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="Email já cadastrado")

    user = User(
        id=str(uuid4()), email=payload.email.lower(),
        hashed_password=get_password_hash(payload.password),
        full_name=payload.full_name, role=payload.role,
        phone=payload.phone, oab_number=payload.oab_number,
    )
    db.add(user)
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "users", user.id)
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserResponse)
async def atualizar(
    user_id: str, payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    user = (await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    mudancas = payload.model_dump(exclude_unset=True)
    eh_admin = cu.role.value in ("superadmin", "admin")

    # Não-admin: só edita a PRÓPRIA conta e apenas campos pessoais seguros
    CAMPOS_SELF = {"full_name", "phone", "oab_number",
                   "djen_oab_numero", "djen_oab_uf"}
    if not eh_admin:
        if cu.id != user_id:
            raise HTTPException(status_code=403, detail="Sem permissão")
        extras = set(mudancas) - CAMPOS_SELF
        if extras:
            raise HTTPException(status_code=403,
                                detail=f"Campos restritos a admin: {sorted(extras)}")

    for k, v in mudancas.items():
        setattr(user, k, v)
    await criar_audit_log(db, cu.id, cu.role.value, "UPDATE", "users", user_id)
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/{user_id}", response_model=MsgResponse)
async def desativar(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_admin),
):
    """Soft delete — nunca DELETE físico."""
    if user_id == cu.id:
        raise HTTPException(status_code=400, detail="Não pode desativar a si mesmo")
    user = (await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    user.deleted_at = datetime.now(timezone.utc)
    user.is_active = False
    await criar_audit_log(db, cu.id, cu.role.value, "DELETE", "users", user_id)
    await db.commit()
    return MsgResponse(detail="Usuário desativado")


# ═══ URL do calendário ICS pessoal (token HMAC) ═══
from app.routers.calendar_feed import gerar_token_calendario
from app.core.config import get_settings as _gset


@router.get("/me/calendar-url")
async def minha_url_calendario(cu: User = Depends(get_current_user)):
    s = _gset()
    base = s.FRONTEND_URL.rstrip("/")
    token = gerar_token_calendario(cu.id)
    return {"url": f"{base}/api/calendar/{cu.id}/{token}.ics"}
