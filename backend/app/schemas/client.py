# ── app/schemas/client.py ────────────────────────────────────────────────────
from __future__ import annotations
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

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
    pass

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
    observacoes: Optional[str] = None

class ClientResponse(ClientBase):
    id: str
    status: str
    responsavel_id: Optional[str] = None
    created_at: datetime
    class Config:
        from_attributes = True

class ConflitoCheckRequest(BaseModel):
    nome: Optional[str] = None
    cpf: Optional[str] = None
    cnpj: Optional[str] = None
    parte_contraria: Optional[str] = None
