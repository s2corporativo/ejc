# ── app/schemas/client.py ────────────────────────────────────────────────────
from __future__ import annotations
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime, date

class ClientBase(BaseModel):
    tipo: str = "PF"
    nome: Optional[str] = None
    cpf: Optional[str] = None
    # Coluna DATE no banco (models/client.py). Pydantic v2 converte "YYYY-MM-DD"
    # em date automaticamente e rejeita string inválida com 422 ANTES do INSERT
    # (evita o asyncpg DataError 500 quando a string crua ia parar na coluna DATE).
    data_nascimento: Optional[date] = None
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

    @field_validator("data_nascimento", mode="before")
    @classmethod
    def _data_nascimento_vazio_para_none(cls, v):
        # Aceita "" / espaços vindos do formulário como ausência de data (None),
        # em vez de estourar validação. Strings ISO válidas seguem para o parser
        # padrão do Pydantic; inválidas viram 422 (não 500).
        if isinstance(v, str) and not v.strip():
            return None
        return v


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
