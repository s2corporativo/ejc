# ── app/routers/notifications.py ─────────────────────────────────────────────
from __future__ import annotations
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.notification import Notification
from app.schemas.common import MsgResponse

router = APIRouter(prefix="/notifications", tags=["Notificações"])


@router.get("/")
async def listar(
    apenas_nao_lidas: bool = False,
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(Notification).where(Notification.user_id == cu.id)
    if apenas_nao_lidas:
        q = q.where(Notification.lida == False)
    q = q.order_by(Notification.created_at.desc()).limit(limit)
    rows = (await db.execute(q)).scalars().all()

    nao_lidas = (await db.execute(
        select(sqlfunc.count()).where(
            Notification.user_id == cu.id, Notification.lida == False
        )
    )).scalar()

    return {
        "data": [
            {"id": n.id, "titulo": n.titulo, "mensagem": n.mensagem,
             "tipo": n.tipo, "link": n.link, "lida": n.lida,
             "created_at": n.created_at}
            for n in rows
        ],
        "nao_lidas": nao_lidas,
    }


@router.post("/{notif_id}/ler", response_model=MsgResponse)
async def marcar_lida(
    notif_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    res = await db.execute(
        update(Notification)
        .where(Notification.id == notif_id, Notification.user_id == cu.id)
        .values(lida=True, lida_em=datetime.now(timezone.utc))
    )
    if res.rowcount == 0:
        # Notificação inexistente ou de outro usuário: não confirma leitura falsa.
        raise HTTPException(404, "Notificação não encontrada")
    await db.commit()
    return MsgResponse(detail="Notificação lida")


@router.post("/ler-todas", response_model=MsgResponse)
async def marcar_todas(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    await db.execute(
        update(Notification)
        .where(Notification.user_id == cu.id, Notification.lida == False)
        .values(lida=True, lida_em=datetime.now(timezone.utc))
    )
    await db.commit()
    return MsgResponse(detail="Todas marcadas como lidas")


# ═══ Web Push: registro de dispositivo (PWA) ═══
from pydantic import BaseModel as _PB
from app.core.config import get_settings as _gs
from app.models.push import PushSubscription
from uuid import uuid4 as _uuid


class PushSubIn(_PB):
    endpoint: str
    p256dh: str
    auth: str


@router.get("/push/vapid-key")
async def vapid_key(cu: User = Depends(get_current_user)):
    s = _gs()
    if not s.PUSH_ENABLED or not s.VAPID_PUBLIC_KEY:
        return {"enabled": False}
    return {"enabled": True, "public_key": s.VAPID_PUBLIC_KEY}


@router.post("/push/subscribe", status_code=201)
async def push_subscribe(
    payload: PushSubIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    existe = (await db.execute(select(PushSubscription).where(
        PushSubscription.endpoint == payload.endpoint
    ))).scalar_one_or_none()
    if existe:
        existe.user_id = cu.id   # re-associar (mesmo browser, novo login)
    else:
        db.add(PushSubscription(
            id=str(_uuid()), user_id=cu.id,
            endpoint=payload.endpoint,
            p256dh=payload.p256dh, auth=payload.auth,
        ))
    await db.commit()
    return {"detail": "Dispositivo registrado para alertas"}
