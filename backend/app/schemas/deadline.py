# ── app/schemas/deadline.py ──────────────────────────────────────────────────
from __future__ import annotations
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime

class DeadlineCreate(BaseModel):
    titulo: str
    tipo: str = "processual"
    prioridade: str = "media"
    data_prazo: Optional[date] = None        # ou calcular via dias
    data_intimacao: Optional[date] = None
    dias_prazo: Optional[int] = None         # se informado: calcula
    dias_uteis: bool = True                  # CPC=úteis; admin=corridos
    tribunal: Optional[str] = None           # suspensões por tribunal (portarias)
    base_legal: Optional[str] = None
    descricao: Optional[str] = None
    case_id: Optional[str] = None
    responsavel_id: Optional[str] = None

class DeadlineUpdate(BaseModel):
    titulo: Optional[str] = None
    status: Optional[str] = None
    prioridade: Optional[str] = None
    data_prazo: Optional[date] = None
    responsavel_id: Optional[str] = None
    observacoes: Optional[str] = None

class DeadlineResponse(BaseModel):
    id: str
    titulo: str
    tipo: str
    prioridade: str
    status: str
    data_prazo: date
    data_intimacao: Optional[date] = None
    base_legal: Optional[str] = None
    case_id: Optional[str] = None
    responsavel_id: Optional[str] = None
    ciencia_confirmada: bool
    created_at: datetime
    class Config:
        from_attributes = True

class CalcularPrazoRequest(BaseModel):
    data_inicio: date
    dias: int
    dias_uteis: bool = True
    tribunal: Optional[str] = None           # suspensões por tribunal (portarias)
