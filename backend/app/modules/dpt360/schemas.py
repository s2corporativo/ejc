from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class DptCompanySummary(BaseModel):
    id: str
    nome: str
    status: str
    cidade: str | None = None
    estado: str | None = None
    casos: int = 0
    casos_abertos: int = 0
    sinais_criticos: int = 0
    providencias_proximas: int = 0


class DptCaseSummary(BaseModel):
    id: str
    client_id: str
    titulo: str
    area: str
    status: str
    prioridade: str
    risco: str | None = None
    proxima_acao: str | None = None
    proxima_acao_prazo: datetime | None = None


class DptDeadlineSummary(BaseModel):
    id: str
    case_id: str
    titulo: str
    data_prazo: date
    status: str
    prioridade: str
    confirmado: bool = True


class DptPriorityItem(BaseModel):
    tipo: Literal["prazo", "caso"]
    nivel: Literal["critico", "alto", "atencao"]
    company_id: str
    company_name: str
    case_id: str
    title: str
    detail: str
    canonical_path: str
    due_date: date | None = None


class DptDashboardMetrics(BaseModel):
    empresas_acompanhadas: int = 0
    riscos_criticos: int = 0
    providencias_proximas: int = 0
    mudancas_juridicas_hoje: int | None = None
    empresas_potencialmente_impactadas: int | None = None
    diagnosticos_pendentes: int | None = None


class DptDashboardResponse(BaseModel):
    generated_at: datetime
    metrics: DptDashboardMetrics
    companies: list[DptCompanySummary] = Field(default_factory=list)
    cases: list[DptCaseSummary] = Field(default_factory=list)
    deadlines: list[DptDeadlineSummary] = Field(default_factory=list)
    priorities: list[DptPriorityItem] = Field(default_factory=list)
    coverage: Literal["complete"] = "complete"
    notes: list[str] = Field(default_factory=list)
