# ── app/schemas/procuracao.py ────────────────────────────────────────────────
from __future__ import annotations
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime

class ProcuracaoCreate(BaseModel):
    client_id: str
    tipo_poderes: str = "ad_judicia"
    poderes_especiais: Optional[str] = None
    permite_substabelecimento: bool = True
    data_outorga: date
    data_validade: Optional[date] = None
    foro_restrito: Optional[str] = None
    observacoes: Optional[str] = None

class ProcuracaoResponse(BaseModel):
    id: str
    client_id: str
    tipo_poderes: str
    data_outorga: date
    data_validade: Optional[date] = None
    revogada: bool
    created_at: datetime
    class Config:
        from_attributes = True
