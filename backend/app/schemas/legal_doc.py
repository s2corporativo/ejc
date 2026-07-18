# ── app/schemas/legal_doc.py ─────────────────────────────────────────────────
from __future__ import annotations
from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime

class LegalDocCreate(BaseModel):
    titulo: str
    tipo_peca: str
    conteudo: str
    case_id: Optional[str] = None
    ai_generated: bool = False

class LegalDocUpdate(BaseModel):
    titulo: Optional[str] = None
    conteudo: Optional[str] = None
    status: Optional[str] = None

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
