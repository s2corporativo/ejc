# ── app/schemas/fee.py ───────────────────────────────────────────────────────
from __future__ import annotations
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
from decimal import Decimal

class FeeCreate(BaseModel):
    tipo: str = "fixo"
    descricao: str
    valor: Optional[Decimal] = None
    percentual_exito: Optional[Decimal] = None
    data_vencimento: Optional[date] = None
    client_id: str
    case_id: Optional[str] = None
    observacoes: Optional[str] = None

class FeeUpdate(BaseModel):
    descricao: Optional[str] = None
    valor: Optional[Decimal] = None
    status: Optional[str] = None
    data_vencimento: Optional[date] = None
    observacoes: Optional[str] = None

class FeePaymentCreate(BaseModel):
    valor: Decimal
    data_pagamento: date
    forma: Optional[str] = None

class FeeResponse(BaseModel):
    id: str
    tipo: str
    status: str
    descricao: str
    valor: Optional[Decimal] = None
    percentual_exito: Optional[Decimal] = None
    data_vencimento: Optional[date] = None
    data_pagamento: Optional[date] = None
    client_id: str
    case_id: Optional[str] = None
    created_at: datetime
    class Config:
        from_attributes = True
