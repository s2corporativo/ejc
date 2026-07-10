from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ModuleLifecycleStatus = Literal["active", "beta", "hidden", "legacy", "disabled"]


class SystemModuleSettingUpdate(BaseModel):
    enabled: bool = True
    menu_visible: bool = True
    status: ModuleLifecycleStatus = "active"
    replacement_route: str | None = Field(default=None, max_length=255)
    removal_date: date | None = None
    reason: str | None = Field(default=None, max_length=2000)

    @field_validator("replacement_route")
    @classmethod
    def validar_rota_substituta(cls, value: str | None):
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if not value.startswith("/") or value.startswith("//"):
            raise ValueError("A rota substituta deve ser uma rota interna iniciada por '/'.")
        return value

    @field_validator("reason")
    @classmethod
    def normalizar_motivo(cls, value: str | None):
        value = (value or "").strip()
        return value or None

    @model_validator(mode="after")
    def validar_consistencia(self):
        if self.status == "disabled" and self.enabled:
            raise ValueError("Módulo com status disabled deve estar desabilitado.")
        if not self.enabled and self.status != "disabled":
            raise ValueError("Módulo desabilitado deve usar status disabled.")
        if self.status in {"hidden", "disabled"} and self.menu_visible:
            raise ValueError("Módulo oculto ou desabilitado não pode permanecer no menu.")
        return self


class SystemModuleSettingResponse(SystemModuleSettingUpdate):
    model_config = ConfigDict(from_attributes=True)

    module_key: str
    updated_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SystemModuleSettingList(BaseModel):
    data: list[SystemModuleSettingResponse]
    total: int
    protected_module_keys: list[str]
    notice: str
