# ── app/schemas/case_next_action.py ──────────────────────────────────────────
"""Contratos da próxima ação operacional do caso."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


Urgency = Literal["baixa", "media", "alta", "critica"]
WaitingOn = Literal["ninguem", "cliente", "terceiro", "tribunal", "interno"]
OriginType = Literal["manual", "documento", "movimento", "prazo", "tarefa"]


def _datetime_com_fuso(value: datetime, campo: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{campo} deve incluir fuso horário")
    return value


class CaseNextActionCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    owner_id: str = Field(min_length=36, max_length=36)
    due_at: datetime
    urgency: Urgency = "media"
    blocked: bool = False
    blocked_reason: Optional[str] = Field(default=None, max_length=1000)
    waiting_on: WaitingOn = "ninguem"
    origin_type: OriginType = "manual"
    origin_id: Optional[str] = Field(default=None, min_length=36, max_length=36)

    @field_validator("title")
    @classmethod
    def _title_limpo(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("title deve ter ao menos 3 caracteres úteis")
        return value

    @field_validator("due_at")
    @classmethod
    def _due_at_com_fuso(cls, value: datetime) -> datetime:
        return _datetime_com_fuso(value, "due_at")

    @model_validator(mode="after")
    def _coerencia(self):
        if self.blocked:
            reason = (self.blocked_reason or "").strip()
            if len(reason) < 5:
                raise ValueError("blocked_reason é obrigatório quando blocked=true")
            self.blocked_reason = reason
        elif self.blocked_reason:
            raise ValueError("blocked_reason só pode ser informado quando blocked=true")

        if self.waiting_on != "ninguem" and not self.blocked:
            raise ValueError("waiting_on diferente de ninguem exige blocked=true")

        if self.origin_type == "manual" and self.origin_id is not None:
            raise ValueError("origin_id não pode ser informado para origem manual")
        if self.origin_type != "manual" and self.origin_id is None:
            raise ValueError("origin_id é obrigatório para origem não manual")
        return self


class CaseNextActionWaiverCreate(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)
    expires_at: datetime

    @field_validator("reason")
    @classmethod
    def _reason_limpo(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 10:
            raise ValueError("reason deve ter ao menos 10 caracteres úteis")
        return value

    @field_validator("expires_at")
    @classmethod
    def _expiry_valida(cls, value: datetime) -> datetime:
        value = _datetime_com_fuso(value, "expires_at")
        now = datetime.now(timezone.utc)
        if value <= now:
            raise ValueError("expires_at deve estar no futuro")
        if value > now + timedelta(days=90):
            raise ValueError("a exceção não pode exceder 90 dias")
        return value


class CaseNextActionComplete(BaseModel):
    completion_note: Optional[str] = Field(default=None, max_length=2000)
    replacement: Optional[CaseNextActionCreate] = None
    waiver: Optional[CaseNextActionWaiverCreate] = None

    @model_validator(mode="after")
    def _destino_unico(self):
        if self.replacement is not None and self.waiver is not None:
            raise ValueError("informe replacement ou waiver, nunca ambos")
        if self.completion_note is not None:
            self.completion_note = self.completion_note.strip() or None
        return self


class CaseNextActionOut(BaseModel):
    id: str
    case_id: str
    title: str
    owner_id: str
    due_at: datetime
    urgency: Urgency
    blocked: bool
    blocked_reason: Optional[str]
    waiting_on: WaitingOn
    origin_type: OriginType
    origin_id: Optional[str]
    created_by: str
    completed_at: Optional[datetime]
    completed_by: Optional[str]
    completion_note: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CaseNextActionWaiverOut(BaseModel):
    id: str
    case_id: str
    reason: str
    expires_at: datetime
    created_by: str
    created_at: datetime
    revoked_at: Optional[datetime]
    revoked_by: Optional[str]

    class Config:
        from_attributes = True


class CaseOperationalView(BaseModel):
    case_id: str
    estado_operacional: Literal[
        "onboarding",
        "planejamento",
        "em_andamento",
        "aguardando_cliente",
        "aguardando_terceiro",
        "providencia_urgente",
        "negociacao",
        "encerramento",
        "encerrado",
    ]
    next_action: Optional[CaseNextActionOut]
    waiver: Optional[CaseNextActionWaiverOut]
    enforcement_enabled: bool
