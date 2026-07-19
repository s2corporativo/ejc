# ── app/schemas/deadline.py ──────────────────────────────────────────────────
from __future__ import annotations
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import date, datetime

class DeadlineCreate(BaseModel):
    titulo: str
    tipo: str = "processual"
    prioridade: str = "media"
    data_prazo: Optional[date] = None        # ou calcular via dias
    data_intimacao: Optional[date] = None
    dias_prazo: Optional[int] = None         # se informado: calcula
    dias_uteis: bool = True                  # CPC=úteis; admin=corridos
    dobro: bool = False                      # prazo em dobro (CPC 180/183/186/229)
    tribunal: Optional[str] = None           # suspensões por tribunal (portarias)
    base_legal: Optional[str] = None
    descricao: Optional[str] = None
    case_id: Optional[str] = None
    responsavel_id: Optional[str] = None

    @field_validator("tipo")
    @classmethod
    def _tipo_valido(cls, v: str) -> str:
        # Deadline.tipo é SAEnum(DeadlineTipo): valor fora do enum estoura no
        # INSERT (asyncpg InvalidTextRepresentationError → 500). Validar na
        # ENTRADA devolve 422 claro. Import lazy p/ evitar ciclo model↔schema.
        from app.models.deadline import DeadlineTipo
        validos = {m.value for m in DeadlineTipo}
        if v not in validos:
            raise ValueError(f"tipo inválido: use um de {sorted(validos)}")
        return v

    @field_validator("prioridade")
    @classmethod
    def _prioridade_valida(cls, v: str) -> str:
        # Deadline.prioridade é SAEnum(DeadlinePrioridade) — mesma classe de 500.
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
        # Deadline.status é SAEnum(DeadlineStatus): valor fora do enum estourava
        # no UPDATE (500). Vazio/None PASSA (update parcial).
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
        # Deadline.prioridade é SAEnum(DeadlinePrioridade) — mesma classe de 500.
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
    dias: int
    dias_uteis: bool = True
    dobro: bool = False                      # prazo em dobro (CPC 180/183/186/229)
    tribunal: Optional[str] = None           # suspensões por tribunal (portarias)
