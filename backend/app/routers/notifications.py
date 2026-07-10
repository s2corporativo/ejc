# ── app/routers/notifications.py ─────────────────────────────────────────────
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func as sqlfunc
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.audit_log import criar_audit_log
from app.models.notification import Notification, NotificationPreference
from app.models.push import PushSubscription
from app.models.user import User
from app.schemas.common import MsgResponse
from app.schemas.notification_preferences import (
    NotificationPreferenceEnvelope,
    NotificationPreferenceUpdate,
    PushSubscriptionList,
)
from app.services.notification_preferences import (
    get_notification_preference,
    preference_envelope,
)

router = APIRouter(prefix="/notifications", tags=["Notificações"])


def _role_value(user: User) -> str:
    return getattr(user.role, "value", str(user.role))


@router.get("/")
async def listar(
    apenas_nao_lidas: bool = False,
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(Notification).where(Notification.user_id == cu.id)
    if apenas_nao_lidas:
        q = q.where(Notification.lida.is_(False))
    q = q.order_by(Notification.created_at.desc()).limit(limit)
    rows = (await db.execute(q)).scalars().all()

    nao_lidas = (
        await db.execute(
            select(sqlfunc.count()).where(
                Notification.user_id == cu.id,
                Notification.lida.is_(False),
            )
        )
    ).scalar()

    return {
        "data": [
            {
                "id": n.id,
                "titulo": n.titulo,
                "mensagem": n.mensagem,
                "tipo": n.tipo,
                "link": n.link,
                "lida": n.lida,
                "created_at": n.created_at,
            }
            for n in rows
        ],
        "nao_lidas": nao_lidas,
    }


@router.get("/preferences", response_model=NotificationPreferenceEnvelope)
async def obter_preferencias(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    preference = await get_notification_preference(db, cu.id)
    return preference_envelope(cu.id, preference)


@router.put("/preferences", response_model=NotificationPreferenceEnvelope)
async def atualizar_preferencias(
    payload: NotificationPreferenceUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    preference = await get_notification_preference(db, cu.id)
    dados_antes = (
        preference_envelope(cu.id, preference).preferences.model_dump(mode="json")
        if preference
        else None
    )
    if preference is None:
        preference = NotificationPreference(user_id=cu.id)
        db.add(preference)

    for field, value in payload.model_dump().items():
        setattr(preference, field, value)

    dados_depois = payload.model_dump(mode="json")
    await criar_audit_log(
        db,
        user_id=cu.id,
        user_role=_role_value(cu),
        acao="UPDATE",
        entidade="notification_preferences",
        registro_id=cu.id,
        dados_antes=dados_antes,
        dados_depois=dados_depois,
        detalhes="Preferências pessoais de notificações atualizadas.",
    )
    await db.commit()
    await db.refresh(preference)
    return preference_envelope(cu.id, preference)


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
        .where(Notification.user_id == cu.id, Notification.lida.is_(False))
        .values(lida=True, lida_em=datetime.now(timezone.utc))
    )
    await db.commit()
    return MsgResponse(detail="Todas marcadas como lidas")


class PushSubIn(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


@router.get("/push/vapid-key")
async def vapid_key(cu: User = Depends(get_current_user)):
    settings = get_settings()
    if not settings.PUSH_ENABLED or not settings.VAPID_PUBLIC_KEY:
        return {"enabled": False}
    return {"enabled": True, "public_key": settings.VAPID_PUBLIC_KEY}


@router.get("/push/subscriptions", response_model=PushSubscriptionList)
async def listar_dispositivos_push(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    rows = (
        await db.execute(
            select(PushSubscription)
            .where(PushSubscription.user_id == cu.id)
            .order_by(PushSubscription.created_at.desc())
        )
    ).scalars().all()
    data = [{"id": row.id, "created_at": row.created_at} for row in rows]
    return {
        "data": data,
        "total": len(data),
        "notice": "Somente identificadores e datas dos seus próprios dispositivos são exibidos.",
    }


@router.delete("/push/subscriptions/{subscription_id}", response_model=MsgResponse)
async def revogar_dispositivo_push(
    subscription_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    subscription = (
        await db.execute(
            select(PushSubscription).where(
                PushSubscription.id == subscription_id,
                PushSubscription.user_id == cu.id,
            )
        )
    ).scalar_one_or_none()
    if subscription is None:
        raise HTTPException(404, "Dispositivo não encontrado")

    await db.delete(subscription)
    await criar_audit_log(
        db,
        user_id=cu.id,
        user_role=_role_value(cu),
        acao="DELETE",
        entidade="push_subscriptions",
        registro_id=subscription_id,
        detalhes="Dispositivo de Web Push revogado pelo próprio usuário.",
    )
    await db.commit()
    return MsgResponse(detail="Dispositivo revogado")


@router.post("/push/subscribe", status_code=201)
async def push_subscribe(
    payload: PushSubIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    existente = (
        await db.execute(
            select(PushSubscription).where(
                PushSubscription.endpoint == payload.endpoint
            )
        )
    ).scalar_one_or_none()
    if existente and existente.user_id != cu.id:
        raise HTTPException(409, "Este dispositivo já está associado a outra conta")

    if existente:
        existente.p256dh = payload.p256dh
        existente.auth = payload.auth
        subscription_id = existente.id
    else:
        subscription_id = str(uuid4())
        db.add(
            PushSubscription(
                id=subscription_id,
                user_id=cu.id,
                endpoint=payload.endpoint,
                p256dh=payload.p256dh,
                auth=payload.auth,
            )
        )

    await criar_audit_log(
        db,
        user_id=cu.id,
        user_role=_role_value(cu),
        acao="CREATE" if existente is None else "UPDATE",
        entidade="push_subscriptions",
        registro_id=subscription_id,
        detalhes="Dispositivo de Web Push inscrito pelo próprio usuário.",
    )
    await db.commit()
    return {"detail": "Dispositivo registrado para alertas"}
