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


def whatsapp_configurado(settings: Settings | None = None) -> bool:
    """Configuração COMPLETA do remetente WhatsApp, SEM olhar `WHATSAPP_ENABLED`.

    Fonte ÚNICA da regra de "configurado" para o canal: a disponibilidade das
    preferências (`channel_availability`), a guarda do envio real
    (`notification_service.enviar_whatsapp`) e o inventário de integrações
    (`integration_status.build_integration_status`) derivam TODOS daqui —
    duplicar a regra já produziu painel e envio discordando.

    Exige URL + chave + INSTÂNCIA: `enviar_whatsapp` recusa instância vazia
    antes de tocar a rede, então ambiente com `EVOLUTION_INSTANCE` em branco
    não é canal funcional (todo envio devolveria False em silêncio).
    """
    settings = settings or get_settings()
    return bool(
        (settings.EVOLUTION_API_URL or "").strip()
        and (settings.EVOLUTION_API_KEY or "").strip()
        and (settings.EVOLUTION_INSTANCE or "").strip()
    )


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
        # Remetente = Evolution API (a mesma instância do webhook de ENTRADA
        # passou a cobrir também a SAÍDA). Mesma forma do e-mail acima: a flag
        # sozinha não basta, a configuração precisa estar completa (URL, chave
        # e instância — ver whatsapp_configurado).
        whatsapp=bool(settings.WHATSAPP_ENABLED and whatsapp_configurado(settings)),
    )


def channel_opt_in(
    preference: NotificationPreference | NotificationPreferenceResponse | None,
    field: str,
) -> bool:
    """Opt-in do USUÁRIO para um canal externo (push/email/whatsapp).

    Sem linha de preferências vale o DEFAULT DECLARADO em
    `DEFAULT_PREFERENCES` — que é o mesmo que a API devolve ao usuário em
    `preference_response`. Antes o dispatch tratava `pref is None` como "pode
    tudo": todo usuário que nunca abriu a tela de preferências passaria a
    receber WhatsApp/e-mail externo assim que o canal fosse habilitado no
    ambiente, contrariando o default exibido a ele (opt-in, não opt-out).
    """
    padrao = bool(DEFAULT_PREFERENCES.get(field, False))
    if preference is None:
        return padrao
    return bool(getattr(preference, field, padrao))


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
