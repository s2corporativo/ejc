# ── app/schemas/ajuizamento.py ───────────────────────────────────────────────
# Schemas do núcleo de ajuizamento. Nenhum schema de resposta carrega segredo:
# perfis expõem só referências ao cofre (client_id_ref/certificate_ref).
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class AssuntoIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=20)
    nome: Optional[str] = Field(None, max_length=200)
    principal: bool = False


class DocumentoIn(BaseModel):
    document_id: str = Field(min_length=1, max_length=36)
    document_type: str = Field(pattern="^(procuracao|documento_pessoal|comprovante|probatorio|complementar)$")
    tpu_document_type: Optional[str] = Field(None, max_length=20)
    ordem: int = Field(default=1, ge=1, le=500)


class AdvogadoIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=36)
    tipo: str = Field(default="advogado", pattern="^(advogado|advogado_auxiliar|estagiario)$")
    procuracao_id: Optional[str] = Field(None, max_length=36)


class FilingBase(BaseModel):
    profile_id: Optional[str] = Field(None, max_length=36)
    peticao_legal_doc_id: Optional[str] = Field(None, max_length=36)
    tribunal_code: Optional[str] = Field(None, max_length=10)
    system: Optional[str] = Field(None, pattern="^(pdpj|pje_mni|eproc|manual)$")
    segment: Optional[str] = Field(None, max_length=30)
    degree: Optional[str] = Field(None, pattern="^[12]$")
    environment: Optional[str] = Field(None, pattern="^(homologacao|producao)$")
    jurisdicao: Optional[str] = Field(None, max_length=120)
    codigo_localidade: Optional[str] = Field(None, max_length=20)
    competencia: Optional[str] = Field(None, max_length=120)
    competencia_codigo: Optional[str] = Field(None, max_length=20)
    classe_codigo: Optional[str] = Field(None, max_length=20)
    classe_nome: Optional[str] = Field(None, max_length=200)
    assuntos: Optional[list[AssuntoIn]] = None
    valor_causa: Optional[Decimal] = Field(None, ge=0)
    nivel_sigilo: Optional[int] = Field(None, ge=0, le=5)
    gratuidade: Optional[bool] = None
    tutela: Optional[bool] = None
    prioridade: Optional[str] = Field(None, max_length=40)
    caracteristicas: Optional[dict[str, Any]] = None
    documentos: Optional[list[DocumentoIn]] = None
    advogados: Optional[list[AdvogadoIn]] = None

    @field_validator("caracteristicas")
    @classmethod
    def _caracteristicas_simples(cls, v):
        if v is None:
            return v
        if len(v) > 50:
            raise ValueError("no máximo 50 características")
        for k, val in v.items():
            if len(str(k)) > 60 or (isinstance(val, str) and len(val) > 2000):
                raise ValueError("característica muito longa")
            if not isinstance(val, (str, int, float, bool)) and val is not None:
                raise ValueError("característica deve ser valor simples")
        return v


class FilingCreate(FilingBase):
    case_id: str = Field(min_length=1, max_length=36)


class FilingUpdate(FilingBase):
    pass


class AprovarReq(BaseModel):
    confirmacao: str = Field(min_length=1, max_length=60)
    observacoes: Optional[str] = Field(None, max_length=2000)


class AssinarReq(BaseModel):
    provider: str = Field(default="registro_externo", pattern="^(registro_externo|pje_office|a1|a3_pkcs11|psc_nuvem)$")
    certificate_subject: Optional[str] = Field(None, max_length=300)
    certificate_serial: Optional[str] = Field(None, max_length=80)
    algorithm: Optional[str] = Field(None, max_length=30)
    signed_document_id: Optional[str] = Field(None, max_length=36)
    signed_document_hash: Optional[str] = Field(None, min_length=64, max_length=64)


class ConfirmarManualReq(BaseModel):
    cnj_number: Optional[str] = Field(None, max_length=30)
    external_protocol: Optional[str] = Field(None, max_length=120)
    external_process_id: Optional[str] = Field(None, max_length=120)
    distribution_unit: Optional[str] = Field(None, max_length=200)
    receipt_document_id: Optional[str] = Field(None, max_length=36)
    protocolado_em: Optional[datetime] = None

    @field_validator("protocolado_em")
    @classmethod
    def _nao_futuro(cls, v):
        if v is None:
            return v
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        if v > datetime.now(timezone.utc):
            raise ValueError("protocolado_em não pode estar no futuro")
        return v


class CancelarReq(BaseModel):
    motivo: Optional[str] = Field(None, max_length=500)


class PerfilIn(BaseModel):
    tribunal_code: Optional[str] = Field(None, max_length=10)
    tribunal_nome: Optional[str] = Field(None, max_length=120)
    segment: Optional[str] = Field(None, max_length=30)
    degree: Optional[str] = Field(None, pattern="^[12]$")
    system: Optional[str] = Field(None, pattern="^(pdpj|pje_mni|eproc|datajud|manual)$")
    environment: Optional[str] = Field(None, pattern="^(homologacao|producao)$")
    integration_type: Optional[str] = Field(None, pattern="^(rest|soap|portal)$")
    base_url: Optional[str] = Field(None, max_length=500)
    api_version: Optional[str] = Field(None, max_length=20)
    auth_type: Optional[str] = Field(None, max_length=30)
    client_id_ref: Optional[str] = Field(None, max_length=120)
    certificate_ref: Optional[str] = Field(None, max_length=120)
    certificate_required: Optional[bool] = None
    filing_supported: Optional[bool] = None
    append_petition_supported: Optional[bool] = None
    process_query_supported: Optional[bool] = None
    movement_query_supported: Optional[bool] = None
    document_download_supported: Optional[bool] = None
    notice_query_supported: Optional[bool] = None
    callback_supported: Optional[bool] = None
    authorized: Optional[bool] = None
    production_endpoint_verified: Optional[bool] = None
    credentials_valid: Optional[bool] = None
    homologation_checklist: Optional[dict[str, Any]] = None
    homologated_at: Optional[datetime] = None
    documentation_url: Optional[str] = Field(None, max_length=500)
    ativo: Optional[bool] = None

    @field_validator("client_id_ref", "certificate_ref")
    @classmethod
    def _so_referencia(cls, v):
        if v is None or v == "":
            return None
        if ":" not in v:
            raise ValueError("informe referência 'provider_key:field_key' ao cofre — nunca o valor da credencial")
        return v


class PerfilCreate(PerfilIn):
    tribunal_code: str = Field(min_length=2, max_length=10)
    system: str = Field(pattern="^(pdpj|pje_mni|eproc|datajud|manual)$")


class TpuSyncReq(BaseModel):
    tipo: str = Field(pattern="^(classe|assunto|movimento|documento)$")
    termo: str = Field(min_length=1, max_length=200)
    tipo_pesquisa: str = Field(default="N", pattern="^[GNC]$")


class TpuImportReq(BaseModel):
    tipo: str = Field(pattern="^(classe|assunto|movimento|documento)$")
    origem: str = Field(default="carga_manual", max_length=40)
    itens: list[dict[str, Any]] = Field(min_length=1, max_length=5000)
