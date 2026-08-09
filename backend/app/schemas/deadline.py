# ── app/schemas/deadline.py ──────────────────────────────────────────────────
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

RegimeProcessual = Literal["civel", "trabalhista", "penal"]


class DeadlineCreate(BaseModel):
    titulo: str
    tipo: str = "processual"
    prioridade: str = "media"
    data_prazo: Optional[date] = None
    data_intimacao: Optional[date] = None
    dias_prazo: Optional[int] = Field(default=None, ge=1, le=3650)
    dias_uteis: bool = True
    dobro: bool = False
    tribunal: Optional[str] = None
    regime_processual: Optional[RegimeProcessual] = None
    excecao_recesso_penal: bool = False
    base_legal: Optional[str] = None
    descricao: Optional[str] = None
    case_id: Optional[str] = None
    responsavel_id: Optional[str] = None

    @field_validator("tipo")
    @classmethod
    def _tipo_valido(cls, v: str) -> str:
        from app.models.deadline import DeadlineTipo

        validos = {m.value for m in DeadlineTipo}
        if v not in validos:
            raise ValueError(f"tipo inválido: use um de {sorted(validos)}")
        return v

    @field_validator("prioridade")
    @classmethod
    def _prioridade_valida(cls, v: str) -> str:
        from app.models.deadline import DeadlinePrioridade

        validos = {m.value for m in DeadlinePrioridade}
        if v not in validos:
            raise ValueError(f"prioridade inválida: use uma de {sorted(validos)}")
        return v


class DeadlineUpdate(BaseModel):
    titulo: Optional[str] = None
    status: Optional[str] = None
    prioridade: Optional[str] = None
    data_prazo: Optional[date] = None
    responsavel_id: Optional[str] = None
    observacoes: Optional[str] = None

    @field_validator("status")
    @classmethod
    def _status_valido(cls, v: Optional[str]) -> Optional[str]:
        if v is None or str(v).strip() == "":
            return v
        from app.models.deadline import DeadlineStatus

        validos = {m.value for m in DeadlineStatus}
        if v not in validos:
            raise ValueError(f"status inválido: use um de {sorted(validos)}")
        return v

    @field_validator("prioridade")
    @classmethod
    def _prioridade_valida(cls, v: Optional[str]) -> Optional[str]:
        if v is None or str(v).strip() == "":
            return v
        from app.models.deadline import DeadlinePrioridade

        validos = {m.value for m in DeadlinePrioridade}
        if v not in validos:
            raise ValueError(f"prioridade inválida: use uma de {sorted(validos)}")
        return v


class DeadlineResponse(BaseModel):
    id: str
    titulo: str
    tipo: str
    prioridade: str
    status: str
    data_prazo: date
    data_intimacao: Optional[date] = None
    data_publicacao: Optional[date] = None
    termo_inicial: Optional[date] = None
    regime_calculo: Optional[str] = None
    calculo_automatico: bool = False
    base_legal: Optional[str] = None
    case_id: Optional[str] = None
    responsavel_id: Optional[str] = None
    ciencia_confirmada: bool
    confirmado: bool = True
    origem: Optional[str] = None
    origem_documento_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class CalcularPrazoRequest(BaseModel):
    data_inicio: date
    dias: int = Field(ge=1, le=3650)
    dias_uteis: bool = True
    dobro: bool = False
    tribunal: Optional[str] = None
    regime_processual: Optional[RegimeProcessual] = None
    aplicar_recesso: bool = True
    excecao_recesso_penal: bool = False
