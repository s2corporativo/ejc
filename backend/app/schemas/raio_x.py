"""Contratos HTTP do Raio-X do Processo."""
from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


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


class RaioXIdentificacaoRevisada(BaseModel):
    """Allowlist explícita para ``revisao_humana.identificacao`` no PATCH.

    Issue #695: o dict livre enviado pelo cliente era iterado com
    ``setattr(analise, key, value)`` em qualquer atributo existente no model
    (status, deleted_at, created_by, id, titulo...) — mass assignment. Aqui só
    os mesmos campos de identificação processual que ``_aplicar_identificacao``
    trata (raio_x.py) são aceitos, com os mesmos limites de tamanho de
    ``RaioXUpdate``. Qualquer chave fora deste conjunto é rejeitada em
    ``atualizar()`` (raio_x.py) com 422 nomeando os campos recusados —
    ``extra="forbid"`` aqui é defesa em profundidade, não a mensagem ao
    cliente (essa é construída no router, para poder listar os nomes).
    """

    model_config = {"extra": "forbid"}

    numero_processo: Optional[str] = Field(None, max_length=30)
    area: Optional[str] = Field(None, max_length=50)
    subarea: Optional[str] = Field(None, max_length=100)
    rito: Optional[str] = Field(None, max_length=100)
    fase: Optional[str] = Field(None, max_length=100)
    tribunal: Optional[str] = Field(None, max_length=50)
    orgao: Optional[str] = Field(None, max_length=100)
    unidade: Optional[str] = Field(None, max_length=100)
    posicao_cliente: Optional[str] = Field(None, max_length=100)


class ClienteConversao(BaseModel):
    modo: Literal["existente", "novo"]
    client_id: Optional[str] = None
    nome: Optional[str] = Field(None, max_length=255)
    cpf: Optional[str] = Field(None, max_length=20)
    cnpj: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    telefone: Optional[str] = Field(None, max_length=30)

    @model_validator(mode="before")
    @classmethod
    def normalizar_documento(cls, data: Any) -> Any:
        """Aceita o contrato legado CPF/CNPJ sem classificar PJ como PF.

        A interface antiga enviava qualquer documento pelo campo ``cpf``. Quando
        houver 12 a 14 dígitos e ``cnpj`` estiver vazio, o valor é promovido para
        CNPJ. Comprimento fora de 11/14 ou dígito verificador inválido é ERRO
        explícito — nunca truncamento silencioso (P0-473).
        """
        from app.services.validators_service import validar_cnpj, validar_cpf

        if not isinstance(data, dict):
            return data
        result = dict(data)
        cpf = re.sub(r"\D", "", str(result.get("cpf") or ""))
        cnpj = re.sub(r"\D", "", str(result.get("cnpj") or ""))
        if not cnpj and len(cpf) > 11:
            cnpj, cpf = cpf, ""
        if cpf:
            if len(cpf) != 11:
                raise ValueError(
                    f"CPF deve ter 11 dígitos (recebido: {len(cpf)})"
                )
            if not validar_cpf(cpf):
                raise ValueError("CPF com dígito verificador inválido")
        if cnpj:
            if len(cnpj) != 14:
                raise ValueError(
                    f"CNPJ deve ter 14 dígitos (recebido: {len(cnpj)})"
                )
            if not validar_cnpj(cnpj):
                raise ValueError("CNPJ com dígito verificador inválido")
        result["cpf"] = cpf or None
        result["cnpj"] = cnpj or None
        if isinstance(result.get("client_id"), str):
            result["client_id"] = result["client_id"].strip() or None
        if isinstance(result.get("nome"), str):
            result["nome"] = result["nome"].strip() or None
        return result

    @model_validator(mode="after")
    def validar_modo(self):
        if self.modo == "existente" and not self.client_id:
            raise ValueError("Selecione um cliente existente")
        if self.modo == "novo" and not (self.nome or self.cpf or self.cnpj):
            raise ValueError("Informe os dados mínimos do novo cliente")
        return self


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
