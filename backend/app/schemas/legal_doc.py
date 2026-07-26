# ── app/schemas/legal_doc.py ─────────────────────────────────────────────────
from __future__ import annotations
from pydantic import BaseModel, field_validator
from typing import Optional, Any
from datetime import datetime, timezone

class LegalDocCreate(BaseModel):
    titulo: str
    tipo_peca: str
    conteudo: str
    case_id: Optional[str] = None
    # DOC-059: `ai_generated` NÃO é aceito do cliente. A criação manual por este
    # endpoint nasce sempre ai_generated=False (derivado no servidor); peças de
    # origem IA são criadas pelos fluxos de geração (services/geracao_documental,
    # peca_service, ...) que setam ai_generated=True diretamente no model. Confiar
    # no cliente aqui permitiria burlar o enforcement HITL.

    @field_validator("tipo_peca")
    @classmethod
    def _tipo_peca_valido(cls, v: str) -> str:
        # LegalDoc.tipo_peca é SAEnum(PecaTipo): valor fora do enum estoura no
        # INSERT (asyncpg InvalidTextRepresentationError → 500). Validar na
        # ENTRADA devolve 422. Import lazy p/ evitar ciclo model↔schema.
        from app.models.legal_doc import PecaTipo
        validos = {m.value for m in PecaTipo}
        if v not in validos:
            raise ValueError(f"tipo_peca inválido: use um de {sorted(validos)}")
        return v

class LegalDocUpdate(BaseModel):
    titulo: Optional[str] = None
    conteudo: Optional[str] = None
    status: Optional[str] = None

    @field_validator("status")
    @classmethod
    def _status_valido(cls, v: Optional[str]) -> Optional[str]:
        # LegalDoc.status é SAEnum(PecaStatus) — valor fora do enum estourava no
        # UPDATE (500). Vazio/None PASSA (update parcial).
        if v is None or str(v).strip() == "":
            return v
        from app.models.legal_doc import PecaStatus
        validos = {m.value for m in PecaStatus}
        if v not in validos:
            raise ValueError(f"status inválido: use um de {sorted(validos)}")
        return v

class LegalDocRevisao(BaseModel):
    aprovado: bool
    notas: Optional[str] = None

class LegalDocAprovacao(BaseModel):
    # BUG-08: aprovação HITL. Para peça ai_generated, observacoes é obrigatório.
    observacoes: Optional[str] = None

class LegalDocProtocolo(BaseModel):
    # Registro do comprovante de protocolo (peticionamento manual). numero_protocolo
    # é obrigatório (a rota rejeita vazio); os demais são opcionais.
    numero_protocolo: str
    protocolo_tribunal: Optional[str] = None
    protocolado_em: Optional[datetime] = None
    protocolo_comprovante_doc_id: Optional[str] = None

    @field_validator("protocolado_em")
    @classmethod
    def _protocolado_em_nao_futuro(cls, v: Optional[datetime]) -> Optional[datetime]:
        # B3: protocolo no FUTURO não existe — data futura falsificaria a prova
        # de tempestividade. Naive é interpretado como UTC (mesmo referencial
        # do default datetime.now(timezone.utc) usado na rota).
        if v is None:
            return v
        ref = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if ref > datetime.now(timezone.utc):
            raise ValueError("protocolado_em não pode estar no futuro")
        return v

class LegalDocResponse(BaseModel):
    id: str
    titulo: str
    tipo_peca: str
    status: str
    versao: int
    ai_generated: bool
    human_reviewed: bool
    case_id: Optional[str] = None
    revisor_id: Optional[str] = None
    validacao_juridica: Optional[dict[str, Any]] = None
    created_at: datetime
    class Config:
        from_attributes = True

class LegalDocDetail(LegalDocResponse):
    conteudo: str
    notas_revisao: Optional[str] = None
    numero_protocolo: Optional[str] = None
    protocolado_em: Optional[datetime] = None
    protocolo_tribunal: Optional[str] = None
    protocolo_comprovante_doc_id: Optional[str] = None


class LegalDocRevisaoItem(BaseModel):
    # DOC-056: item do histórico imutável de revisões (metadados, sem conteúdo).
    id: str
    legal_doc_id: str
    revisao: int
    content_hash: Optional[str] = None
    origem: Optional[str] = None
    gerado_por: Optional[str] = None
    criado_em: Optional[datetime] = None
    imutavel: bool = True
    class Config:
        from_attributes = True


class LegalDocRevisaoDetalhe(LegalDocRevisaoItem):
    # Recuperação de uma versão anterior: inclui o conteúdo preservado.
    conteudo: str
