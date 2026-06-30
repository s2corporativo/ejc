# ── app/schemas/ai.py ────────────────────────────────────────────────────────
from __future__ import annotations
from pydantic import BaseModel
from typing import Optional, List

class AnalisarCasoRequest(BaseModel):
    descricao_fatos: str
    area: str
    case_id: Optional[str] = None
    nomes_proteger: Optional[List[str]] = None   # cliente, parte contrária

class ResumirDocRequest(BaseModel):
    texto: str
    case_id: Optional[str] = None

class HITLRevisaoRequest(BaseModel):
    status: str   # revisado | aplicado | descartado
