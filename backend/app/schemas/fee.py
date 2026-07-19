# ── app/schemas/fee.py ───────────────────────────────────────────────────────
from __future__ import annotations
from pydantic import BaseModel, condecimal, field_validator
from typing import Optional
from datetime import date, datetime
from decimal import Decimal

from app.models.fee import FeeTipo

# Valores monetários nunca negativos (auditoria 2026-06-30, M5).
ValorNaoNegativo = condecimal(ge=0)
PercentualNaoNegativo = condecimal(ge=0, le=100)

# Fonte única de verdade: os valores aceitos em `tipo` na CRIAÇÃO são os da enum
# FeeTipo (inclui 'sucumbencia' desde a migration 097). Mantemos o campo como
# `str` — o router faz Fee(**payload.model_dump()) e a coluna é SAEnum(FeeTipo),
# que aceita a string — logo a validação não muda o fluxo de dados, apenas
# rejeita valores fora do domínio (evita 500/erro de enum no banco).
_TIPOS_FEE_VALIDOS = frozenset(t.value for t in FeeTipo)

class FeeCreate(BaseModel):
    tipo: str = "fixo"
    descricao: str
    valor: Optional[ValorNaoNegativo] = None
    percentual_exito: Optional[PercentualNaoNegativo] = None
    data_vencimento: Optional[date] = None
    client_id: str
    case_id: Optional[str] = None
    observacoes: Optional[str] = None

    @field_validator("tipo")
    @classmethod
    def _validar_tipo(cls, v: str) -> str:
        if v not in _TIPOS_FEE_VALIDOS:
            raise ValueError(
                "tipo de honorário inválido: "
                f"{v!r}. Valores permitidos: {sorted(_TIPOS_FEE_VALIDOS)}"
            )
        return v

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
