from __future__ import annotations

from datetime import datetime, time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models.notification import NotificationPreference
from app.schemas.notification_preferences import (
    NotificationChannelAvailability,
    NotificationPreferenceEnvelope,
    NotificationPreferenceResponse,
)

MANDATORY_INTERNAL_TYPES = [
    "prazo",
    "intimacao",
    "audiencia",
    "sistema",
    "auditoria",
]

DEFAULT_PREFERENCES: dict[str, Any] = {
    "push_enabled": True,
    "email_enabled": False,
    "whatsapp_enabled": False,
    "prazos_enabled": True,
    "tarefas_enabled": True,
    "intimacoes_enabled": True,
    "audiencias_enabled": True,
    "documentos_enabled": True,
    "assinaturas_enabled": True,
    "financeiro_enabled": False,
    "diario_oficial_enabled": True,
    "resumo_diario": False,
    "quiet_hours_start": None,
    "quiet_hours_end": None,
    "timezone": "America/Sao_Paulo",
}

CATEGORY_FIELD_BY_TYPE = {
    "prazo": "prazos_enabled",
    "tarefa": "tarefas_enabled",
    "intimacao": "intimacoes_enabled",
    "audiencia": "audiencias_enabled",
    "documento": "documentos_enabled",
    "assinatura": "assinaturas_enabled",
    "honorario": "financeiro_enabled",
    "financeiro": "financeiro_enabled",
    "diario_oficial": "diario_oficial_enabled",
}


def channel_availability(
    settings: Settings | None = None,
) -> NotificationChannelAvailability:
    settings = settings or get_settings()
    return NotificationChannelAvailability(
        push=bool(
            settings.PUSH_ENABLED
            and settings.VAPID_PUBLIC_KEY
            and settings.VAPID_PRIVATE_KEY
        ),
        email=bool(
            settings.EMAIL_ENABLED
            and settings.SMTP_HOST
            and settings.SMTP_USER
            and settings.SMTP_PASSWORD
        ),
        # Vendor Z-API removido → não há remetente automático de WhatsApp. O
        # canal fica sempre indisponível (mesmo com WHATSAPP_ENABLED), até que um
        # novo backend de envio seja plugado. A Evolution API cobre só ENTRADA.
        whatsapp=False,
    )


async def get_notification_preference(
    db: AsyncSession,
    user_id: str,
) -> NotificationPreference | None:
    return (
        await db.execute(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id
            )
        )
    ).scalar_one_or_none()


def preference_response(
    user_id: str,
    preference: NotificationPreference | None,
) -> NotificationPreferenceResponse:
    if preference is None:
        return NotificationPreferenceResponse(
            user_id=user_id,
            created_at=None,
            updated_at=None,
            **DEFAULT_PREFERENCES,
        )
    return NotificationPreferenceResponse.model_validate(preference)


def preference_envelope(
    user_id: str,
    preference: NotificationPreference | None,
    settings: Settings | None = None,
) -> NotificationPreferenceEnvelope:
    response = preference_response(user_id, preference)
    available = channel_availability(settings)
    effective = NotificationChannelAvailability(
        push=response.push_enabled and available.push,
        email=response.email_enabled and available.email,
        whatsapp=response.whatsapp_enabled and available.whatsapp,
    )
    return NotificationPreferenceEnvelope(
        preferences=response,
        available_channels=available,
        effective_channels=effective,
        mandatory_internal_types=MANDATORY_INTERNAL_TYPES,
        notice=(
            "As preferências controlam canais externos e categorias opcionais. "
            "Alertas internos críticos permanecem visíveis no EJC."
        ),
    )


def category_enabled(
    preference: NotificationPreference | NotificationPreferenceResponse | None,
    notification_type: str,
) -> bool:
    if preference is None:
        return True
    field = CATEGORY_FIELD_BY_TYPE.get(notification_type)
    if not field:
        return True
    return bool(getattr(preference, field, True))


def is_quiet_hours(
    now_local: datetime,
    start: time | None,
    end: time | None,
) -> bool:
    if start is None or end is None or start == end:
        return False
    current = now_local.time().replace(tzinfo=None)
    if start < end:
        return start <= current < end
    return current >= start or current < end
