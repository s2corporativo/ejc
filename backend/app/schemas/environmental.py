# ── app/schemas/environmental.py ─────────────────────────────────────────────
from __future__ import annotations
from pydantic import BaseModel, field_validator
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

    @field_validator("orgao_autuador")
    @classmethod
    def _orgao_valido(cls, v: str) -> str:
        # EnvironmentalCase.orgao_autuador é SAEnum(OrgaoAutuador): valor fora do
        # enum estoura no INSERT (asyncpg → 500). Validar na ENTRADA devolve 422.
        from app.models.environmental import OrgaoAutuador
        validos = {m.value for m in OrgaoAutuador}
        if v not in validos:
            raise ValueError(f"orgao_autuador inválido: use um de {sorted(validos)}")
        return v

class EnvCaseUpdate(BaseModel):
    data_ciencia: Optional[date] = None
    status_defesa: Optional[str] = None
    valor_multa: Optional[Decimal] = None
    valor_multa_convertida: Optional[Decimal] = None
    servico_ambiental: Optional[str] = None
    resultado_julgamento: Optional[str] = None
    observacoes: Optional[str] = None

    @field_validator("status_defesa")
    @classmethod
    def _status_defesa_valido(cls, v: Optional[str]) -> Optional[str]:
        # EnvironmentalCase.status_defesa é SAEnum(StatusDefesa) — valor fora do
        # enum estourava no UPDATE (500). Vazio/None PASSA (update parcial).
        if v is None or str(v).strip() == "":
            return v
        from app.models.environmental import StatusDefesa
        validos = {m.value for m in StatusDefesa}
        if v not in validos:
            raise ValueError(f"status_defesa inválido: use um de {sorted(validos)}")
        return v

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
    class Config:
        from_attributes = True
