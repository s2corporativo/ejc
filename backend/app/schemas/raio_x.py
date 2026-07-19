"""Contratos HTTP do Raio-X do Processo."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


STATUS_RAIO_X = {
    "novo", "em_processamento", "aguardando_conferencia", "em_analise",
    "documentos_pendentes", "analise_concluida", "nao_convertido",
    "convertido_em_caso", "descartado", "arquivado",
}


class RaioXCreate(BaseModel):
    titulo: str = Field(min_length=3, max_length=255)
    potencial_cliente: Optional[str] = Field(None, max_length=255)
    retention_days: int = Field(90, ge=7, le=3650)


class RaioXUpdate(BaseModel):
    titulo: Optional[str] = Field(None, min_length=3, max_length=255)
    potencial_cliente: Optional[str] = Field(None, max_length=255)
    status: Optional[str] = None
    numero_processo: Optional[str] = Field(None, max_length=30)
    area: Optional[str] = Field(None, max_length=50)
    subarea: Optional[str] = Field(None, max_length=100)
    rito: Optional[str] = Field(None, max_length=100)
    fase: Optional[str] = Field(None, max_length=100)
    tribunal: Optional[str] = Field(None, max_length=50)
    orgao: Optional[str] = Field(None, max_length=100)
    unidade: Optional[str] = Field(None, max_length=100)
    posicao_cliente: Optional[str] = Field(None, max_length=100)
    revisao_humana: Optional[dict[str, Any]] = None

    @field_validator("status")
    @classmethod
    def validar_status(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in STATUS_RAIO_X:
            raise ValueError(f"Status inválido: {value}")
        return value


class ClienteConversao(BaseModel):
    modo: Literal["existente", "novo"]
    client_id: Optional[str] = None
    nome: Optional[str] = Field(None, max_length=255)
    cpf: Optional[str] = Field(None, max_length=20)
    cnpj: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    telefone: Optional[str] = Field(None, max_length=30)


class CasoConversao(BaseModel):
    titulo: str = Field(min_length=3, max_length=255)
    area: str = Field(max_length=50)
    prioridade: Literal["baixa", "media", "alta", "critica"] = "media"
    numero_processo: Optional[str] = Field(None, max_length=30)
    tribunal: Optional[str] = Field(None, max_length=20)
    comarca: Optional[str] = Field(None, max_length=100)
    vara: Optional[str] = Field(None, max_length=100)
    parte_contraria: Optional[str] = Field(None, max_length=255)
    descricao_fatos: Optional[str] = None
    case_type: str = Field("judicial", max_length=50)


class RaioXConverterRequest(BaseModel):
    cliente: ClienteConversao
    caso: CasoConversao
    documento_ids: list[str] = Field(default_factory=list)
    transferir_prazos: bool = False
    transferir_tarefas: bool = False
    duplicate_confirmed: bool = False
    conflict_confirmed: bool = False
    confirmacao: Literal["TRANSFORMAR EM CASO DO ESCRITÓRIO"]


class RaioXAcaoRequest(BaseModel):
    observacao: Optional[str] = Field(None, max_length=1000)
