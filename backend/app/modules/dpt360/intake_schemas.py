from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


class DptInboundOpportunity(BaseModel):
    origem: Literal["site_depaulateixeira", "manual", "acionejus"]
    pagina: str | None = Field(default=None, max_length=500)
    campanha: str | None = Field(default=None, max_length=160)
    assunto: str = Field(min_length=3, max_length=300)
    mensagem: str = Field(min_length=10, max_length=8000)
    empresa: str | None = Field(default=None, max_length=240)
    contato: str | None = Field(default=None, max_length=180)
    email: EmailStr | None = None
    telefone: str | None = Field(default=None, max_length=40)
    urgencia_declarada: Literal["baixa", "normal", "alta", "critica"] = "normal"
    consentimento_privacidade: bool = False
    external_ref: str | None = Field(default=None, max_length=160)

    @field_validator("origem")
    @classmethod
    def bloquear_acionejus(cls, value: str) -> str:
        if value == "acionejus":
            raise ValueError(
                "Encaminhamento AcioneJus permanece desativado até revisão ética/comercial."
            )
        return value


class DptInboundOpportunityOut(BaseModel):
    intake_id: str
    status: Literal["triagem_pendente"]
    origem: str
    created_at: str | None = None
    next_step: str
