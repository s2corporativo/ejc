from datetime import datetime, time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.notification_preferences import NotificationPreferenceUpdate
from app.services.notification_preferences import (
    MANDATORY_INTERNAL_TYPES,
    category_enabled,
    channel_availability,
    is_quiet_hours,
    preference_envelope,
)


def test_default_envelope_preserva_alertas_internos_criticos():
    payload = preference_envelope("user-1", None, Settings(_env_file=None))

    assert payload.preferences.user_id == "user-1"
    assert payload.preferences.push_enabled is True
    assert "prazo" in payload.mandatory_internal_types
    assert "auditoria" in payload.mandatory_internal_types
    assert payload.mandatory_internal_types == MANDATORY_INTERNAL_TYPES


def test_channel_availability_exige_flag_e_configuracao_completa():
    settings = Settings(
        _env_file=None,
        PUSH_ENABLED=True,
        VAPID_PUBLIC_KEY="public",
        VAPID_PRIVATE_KEY="private",
        EMAIL_ENABLED=True,
        SMTP_USER="user@example.com",
        SMTP_PASSWORD="secret",
        WHATSAPP_ENABLED=True,
        ZAPI_INSTANCE_ID="instance",
        ZAPI_TOKEN="token",
        ZAPI_CLIENT_TOKEN="client-token",
    )

    availability = channel_availability(settings)

    assert availability.push is True
    assert availability.email is True
    assert availability.whatsapp is True


def test_categoria_opcional_respeita_preferencia():
    preference = SimpleNamespace(
        prazos_enabled=True,
        financeiro_enabled=False,
    )

    assert category_enabled(preference, "prazo") is True
    assert category_enabled(preference, "honorario") is False
    assert category_enabled(preference, "sistema") is True


def test_horario_silencioso_normal_e_cruzando_meia_noite():
    tz = ZoneInfo("America/Sao_Paulo")

    assert is_quiet_hours(
        datetime(2026, 7, 10, 13, 0, tzinfo=tz),
        time(12, 0),
        time(14, 0),
    )
    assert is_quiet_hours(
        datetime(2026, 7, 10, 23, 30, tzinfo=tz),
        time(22, 0),
        time(7, 0),
    )
    assert is_quiet_hours(
        datetime(2026, 7, 10, 6, 30, tzinfo=tz),
        time(22, 0),
        time(7, 0),
    )
    assert not is_quiet_hours(
        datetime(2026, 7, 10, 10, 0, tzinfo=tz),
        time(22, 0),
        time(7, 0),
    )


def test_schema_exige_par_completo_de_horario_silencioso():
    with pytest.raises(ValidationError):
        NotificationPreferenceUpdate(quiet_hours_start=time(22, 0))


def test_schema_rejeita_timezone_inexistente():
    with pytest.raises(ValidationError):
        NotificationPreferenceUpdate(timezone="Timezone/Inexistente")
