# ── app/routers/notifications.py ─────────────────────────────────────────────
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import case as sql_case
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

# Classificação exclusivamente pelo `tipo` persistido. Não inspeciona título ou
# mensagem, evitando inferência jurídica por texto livre. Tipos novos/inesperados
# ficam informativos até decisão explícita de produto.
_TIPOS_CRITICOS = frozenset({"prazo", "intimacao", "audiencia", "auditoria"})
_TIPOS_ATENCAO = frozenset(
    {
        "honorario",
        "financeiro",
        "assinatura",
        "documento",
        "diario_oficial",
        "ambiental",
        "sistema",
    }
)


def _criticidade(tipo: str | None) -> str:
    normalizado = (tipo or "").strip().lower()
    if normalizado in _TIPOS_CRITICOS:
        return "critica"
    if normalizado in _TIPOS_ATENCAO:
        return "atencao"
    return "informativa"


def _role_value(user: User) -> str:
    return getattr(user.role, "value", str(user.role))


@router.get("/")
async def listar(
    apenas_nao_lidas: bool = False,
    limit: int = Query(30, ge=1, le=100),
    page: int | None = Query(None, ge=1),
    page_size: int | None = Query(None, ge=1, le=100),
    ordenar_criticidade: bool = False,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Lista notificações sem quebrar o contrato histórico do sino.

    Sem `page`/`page_size` e sem ordenação nova, a resposta preserva literalmente
    `{data, nao_lidas}` e o mesmo custo de duas queries. A paginação é opt-in;
    somente nesse modo entram `total`, `page` e `page_size`. Criticidade também
    só é exposta quando o consumidor pede paginação ou ordenação por criticidade.
    """
    filtros = [Notification.user_id == cu.id]
    if apenas_nao_lidas:
        filtros.append(Notification.lida.is_(False))

    paginado = page is not None or page_size is not None
    pagina = page or 1
    tamanho = page_size or limit
    modo_avancado = paginado or ordenar_criticidade

    q = select(Notification).where(*filtros)
    if ordenar_criticidade:
        ordem_criticidade = sql_case(
            (Notification.tipo.in_(_TIPOS_CRITICOS), 0),
            (Notification.tipo.in_(_TIPOS_ATENCAO), 1),
            else_=2,
        )
        q = q.order_by(ordem_criticidade, Notification.created_at.desc())
    else:
        q = q.order_by(Notification.created_at.desc())

    if paginado:
        q = q.offset((pagina - 1) * tamanho).limit(tamanho)
    else:
        q = q.limit(limit)
    rows = (await db.execute(q)).scalars().all()

    # Contagem exata e independente do recorte/página exibida. Esta já existia
    # no contrato legado e continua sendo a segunda query do sino.
    nao_lidas = (
        await db.execute(
            select(sqlfunc.count()).where(
                Notification.user_id == cu.id,
                Notification.lida.is_(False),
            )
        )
    ).scalar() or 0

    data = []
    for n in rows:
        item = {
            "id": n.id,
            "titulo": n.titulo,
            "mensagem": n.mensagem,
            "tipo": n.tipo,
            "link": n.link,
            "lida": n.lida,
            "created_at": n.created_at,
        }
        if modo_avancado:
            item["criticidade"] = _criticidade(n.tipo)
        data.append(item)

    resposta = {"data": data, "nao_lidas": int(nao_lidas)}
    if paginado:
        total = (
            await db.execute(
                select(sqlfunc.count()).select_from(Notification).where(*filtros)
            )
        ).scalar() or 0
        resposta.update(
            {
                "total": int(total),
                "page": pagina,
                "page_size": tamanho,
            }
        )
    return resposta


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

    @field_validator("endpoint")
    @classmethod
    def _valida_endpoint(cls, v: str) -> str:
        # SSRF guard: só serviços de push conhecidos via https (ver notification_service).
        from app.services.notification_service import endpoint_push_valido

        if not endpoint_push_valido(v):
            raise ValueError(
                "endpoint de push não permitido — apenas serviços FCM/Mozilla/Apple/WNS via https"
            )
        return v


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
