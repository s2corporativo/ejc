# ── app/schemas/processo_eletronico.py ───────────────────────────────────────
# Schemas Pydantic da integração de processo eletrônico MNI 2.2.2 (Issue #762,
# Fase A). Nenhum schema de resposta carrega segredo (id_consultante/senha)
# — só metadados (last4-like: nunca nem last4, porque MNI não tem formato
# fixo de máscara — aqui simplesmente omitido).
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SincronizarProcessoReq(BaseModel):
    case_id: str = Field(min_length=1)
    numero_cnj: str = Field(min_length=1, max_length=25)


class SincronizarProcessoResp(BaseModel):
    job_id: str
    status: str


class StatusSincronizacaoResp(BaseModel):
    case_id: str
    status: str | None = None
    last_synced_at: datetime | None = None
    docs_novos: int = 0
    mensagem_erro: str | None = None


class CredencialCreateReq(BaseModel):
    tribunal_id: str = Field(min_length=1)
    advogado_id: str = Field(min_length=1)
    tipo: str = Field(pattern="^(mni_sistema|certificado)$")
    id_consultante: str | None = Field(None, max_length=200)
    senha_consultante: str | None = Field(None, max_length=200)
    certificado_ref: str | None = Field(None, max_length=500)
    escopo: str = Field(default="leitura", pattern="^(leitura|leitura_peticionamento)$")


class CredencialMetaResp(BaseModel):
    """Metadados exibíveis — NUNCA inclui id_consultante/senha em claro."""
    id: str
    tribunal_id: str
    advogado_id: str
    tipo: str
    escopo: str
    ativo: bool
    ultima_verificacao: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class TestarCredencialResp(BaseModel):
    estado: str  # enfileirado | ok | falha
    detalhe: str
