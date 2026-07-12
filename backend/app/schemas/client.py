# ── app/schemas/client.py ────────────────────────────────────────────────────
from __future__ import annotations
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime

from app.models.client import ClientStatus

# Etapas do funil de leads (CRM) — mesmas colunas do board CRMLeads.tsx.
ETAPAS_FUNIL = {"lead", "contato", "reuniao", "proposta", "convertido", "perdido"}
_STATUS_VALIDOS = {s.value for s in ClientStatus}

class ClientBase(BaseModel):
    tipo: str = "PF"
    nome: Optional[str] = None
    cpf: Optional[str] = None
    data_nascimento: Optional[str] = None
    profissao: Optional[str] = None
    razao_social: Optional[str] = None
    cnpj: Optional[str] = None
    nome_fantasia: Optional[str] = None
    email: Optional[str] = None
    telefone: Optional[str] = None
    whatsapp: Optional[str] = None
    cep: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = "Betim"
    estado: Optional[str] = "MG"
    origem: Optional[str] = None
    observacoes: Optional[str] = None

class ClientCreate(ClientBase):
    # CRM: o board de leads (CRMLeads.tsx) cria o cliente já com status="lead"
    # e etapa_funil="lead". Antes estes campos não existiam no schema: o
    # Pydantic descartava e o lead nascia "ativo" — sumia do funil e poluía a
    # lista de clientes ativos.
    status: str = ClientStatus.ativo.value
    etapa_funil: Optional[str] = None
    origem_lead: Optional[str] = None
    area_interesse: Optional[str] = None

    @field_validator("status")
    @classmethod
    def _valida_status(cls, v: str) -> str:
        if v not in _STATUS_VALIDOS:
            raise ValueError(f"status inválido; use um de: {sorted(_STATUS_VALIDOS)}")
        return v

    @field_validator("etapa_funil")
    @classmethod
    def _valida_etapa(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ETAPAS_FUNIL:
            raise ValueError(f"etapa_funil inválida; use uma de: {sorted(ETAPAS_FUNIL)}")
        return v

class ClientUpdate(BaseModel):
    nome: Optional[str] = None
    razao_social: Optional[str] = None
    cpf: Optional[str] = None
    cnpj: Optional[str] = None
    email: Optional[str] = None
    telefone: Optional[str] = None
    whatsapp: Optional[str] = None
    cep: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None
    status: Optional[str] = None
    etapa_funil: Optional[str] = None
    origem_lead: Optional[str] = None
    area_interesse: Optional[str] = None
    observacoes: Optional[str] = None

    @field_validator("status")
    @classmethod
    def _valida_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _STATUS_VALIDOS:
            raise ValueError(f"status inválido; use um de: {sorted(_STATUS_VALIDOS)}")
        return v

    @field_validator("etapa_funil")
    @classmethod
    def _valida_etapa(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ETAPAS_FUNIL:
            raise ValueError(f"etapa_funil inválida; use uma de: {sorted(ETAPAS_FUNIL)}")
        return v

class ClientResponse(ClientBase):
    id: str
    status: str
    etapa_funil: Optional[str] = None
    origem_lead: Optional[str] = None
    area_interesse: Optional[str] = None
    responsavel_id: Optional[str] = None
    created_at: datetime
    class Config:
        from_attributes = True

class ConflitoCheckRequest(BaseModel):
    nome: Optional[str] = None
    cpf: Optional[str] = None
    cnpj: Optional[str] = None
    parte_contraria: Optional[str] = None
