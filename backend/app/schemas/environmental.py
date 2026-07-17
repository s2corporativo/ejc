# ── app/schemas/environmental.py ─────────────────────────────────────────────
from __future__ import annotations
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import date, datetime
from decimal import Decimal

class EnvCaseCreate(BaseModel):
    case_id: str
    orgao_autuador: str
    numero_auto: str
    data_lavratura: Optional[date] = None
    data_ciencia: Optional[date] = None      # dispara cálculo do prazo
    especie_infracao: Optional[str] = None
    dispositivo_infringido: Optional[str] = None
    valor_multa: Optional[Decimal] = None
    area_degradada_ha: Optional[Decimal] = None
    bioma: Optional[str] = None
    embargo: Optional[str] = None

class EnvCaseUpdate(BaseModel):
    data_ciencia: Optional[date] = None
    status_defesa: Optional[str] = None
    valor_multa: Optional[Decimal] = None
    valor_multa_convertida: Optional[Decimal] = None
    servico_ambiental: Optional[str] = None
    resultado_julgamento: Optional[str] = None
    observacoes: Optional[str] = None

class EnvCaseResponse(BaseModel):
    id: str
    case_id: str
    orgao_autuador: str
    numero_auto: str
    data_lavratura: Optional[date] = None
    data_ciencia: Optional[date] = None
    valor_multa: Optional[Decimal] = None
    data_prazo_defesa: Optional[date] = None
    status_defesa: str
    valor_multa_convertida: Optional[Decimal] = None
    area_degradada_ha: Optional[Decimal] = None
    bioma: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
