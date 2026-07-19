"""Contratos de entrada e saída da entidade Processo."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_PROCESS_STATUS = {"ativo", "suspenso", "encerrado", "arquivado"}
_PROCESS_TYPES = {
    "judicial",
    "recurso",
    "cautelar",
    "execucao",
    "administrativo",
    "extrajudicial",
    "arbitral",
    "outro",
}


def _validate_process_number(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if len(value) > 30:
        raise ValueError("Número do processo deve ter no máximo 30 caracteres")
    from app.services.validators_service import normalizar_cnj, validar_cnj

    if len(normalizar_cnj(value)) == 20 and not validar_cnj(value):
        raise ValueError("Número CNJ inválido: dígito verificador não confere")
    return value


class ProcessCreate(BaseModel):
    numero_cnj: Optional[str] = None
    instancia: Optional[str] = Field(default=None, max_length=20)
    tribunal: Optional[str] = Field(default=None, max_length=160)
    comarca: Optional[str] = Field(default=None, max_length=160)
    vara: Optional[str] = Field(default=None, max_length=160)
    classe: Optional[str] = Field(default=None, max_length=160)
    fase: Optional[str] = Field(default=None, max_length=40)
    tipo: str = "judicial"
    processo_principal_id: Optional[str] = None
    valor_causa: Optional[Decimal] = None
    status: str = "ativo"
    is_principal: Optional[bool] = None

    @field_validator("numero_cnj")
    @classmethod
    def validate_number(cls, value: Optional[str]) -> Optional[str]:
        return _validate_process_number(value)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in _PROCESS_STATUS:
            raise ValueError(f"Status inválido. Use um de {sorted(_PROCESS_STATUS)}")
        return value

    @field_validator("tipo")
    @classmethod
    def validate_type(cls, value: str) -> str:
        if value not in _PROCESS_TYPES:
            raise ValueError(f"Tipo inválido. Use um de {sorted(_PROCESS_TYPES)}")
        return value


class ProcessUpdate(BaseModel):
    numero_cnj: Optional[str] = None
    instancia: Optional[str] = Field(default=None, max_length=20)
    tribunal: Optional[str] = Field(default=None, max_length=160)
    comarca: Optional[str] = Field(default=None, max_length=160)
    vara: Optional[str] = Field(default=None, max_length=160)
    classe: Optional[str] = Field(default=None, max_length=160)
    fase: Optional[str] = Field(default=None, max_length=40)
    tipo: Optional[str] = None
    processo_principal_id: Optional[str] = None
    valor_causa: Optional[Decimal] = None
    status: Optional[str] = None
    is_principal: Optional[bool] = None

    @field_validator("numero_cnj")
    @classmethod
    def validate_number(cls, value: Optional[str]) -> Optional[str]:
        return _validate_process_number(value)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in _PROCESS_STATUS:
            raise ValueError(f"Status inválido. Use um de {sorted(_PROCESS_STATUS)}")
        return value

    @field_validator("tipo")
    @classmethod
    def validate_type(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in _PROCESS_TYPES:
            raise ValueError(f"Tipo inválido. Use um de {sorted(_PROCESS_TYPES)}")
        return value


class ProcessResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    numero_cnj: Optional[str] = None
    instancia: Optional[str] = None
    tribunal: Optional[str] = None
    comarca: Optional[str] = None
    vara: Optional[str] = None
    classe: Optional[str] = None
    fase: Optional[str] = None
    tipo: str
    processo_principal_id: Optional[str] = None
    valor_causa: Optional[Decimal] = None
    status: str
    is_principal: bool
    archived_at: Optional[datetime] = None
    archive_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ArchiveProcessRequest(BaseModel):
    motivo: Optional[str] = Field(default=None, max_length=1000)
