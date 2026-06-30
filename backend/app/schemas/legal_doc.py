# ── app/schemas/legal_doc.py ─────────────────────────────────────────────────
from __future__ import annotations
from pydantic import BaseModel
from typing import Optional
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
    created_at: datetime
    class Config:
        from_attributes = True

class LegalDocDetail(LegalDocResponse):
    conteudo: str
    notas_revisao: Optional[str] = None
