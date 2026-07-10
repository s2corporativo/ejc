from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NotificationPreferenceUpdate(BaseModel):
    push_enabled: bool = True
    email_enabled: bool = False
    whatsapp_enabled: bool = False

    prazos_enabled: bool = True
    tarefas_enabled: bool = True
    intimacoes_enabled: bool = True
    audiencias_enabled: bool = True
    documentos_enabled: bool = True
    assinaturas_enabled: bool = True
    financeiro_enabled: bool = False
    diario_oficial_enabled: bool = True

    resumo_diario: bool = False
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None
    timezone: str = Field(default="America/Sao_Paulo", min_length=1, max_length=64)

    @model_validator(mode="after")
    def validar_horario_e_timezone(self):
        if (self.quiet_hours_start is None) != (self.quiet_hours_end is None):
            raise ValueError(
                "Horário silencioso exige hora inicial e final, ou ambos vazios."
            )
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Timezone inválido.") from exc
        return self


class NotificationPreferenceResponse(NotificationPreferenceUpdate):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class NotificationChannelAvailability(BaseModel):
    push: bool
    email: bool
    whatsapp: bool


class NotificationPreferenceEnvelope(BaseModel):
    preferences: NotificationPreferenceResponse
    available_channels: NotificationChannelAvailability
    effective_channels: NotificationChannelAvailability
    mandatory_internal_types: list[str]
    notice: str


class PushSubscriptionSafe(BaseModel):
    id: str
    created_at: datetime | None = None


class PushSubscriptionList(BaseModel):
    data: list[PushSubscriptionSafe]
    total: int
    notice: str
