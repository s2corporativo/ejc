from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

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


class DptHealthArea(BaseModel):
    area: str
    classificacao: Literal[
        "Regular", "Atenção", "Alto Risco", "Crítico", "Não avaliado"
    ] = "Não avaliado"
    justificativa: str = "Sem diagnóstico especializado aprovado."
    evidencias: int = 0


class DptTwinDimension(BaseModel):
    key: str
    label: str
    status: Literal["com_dados", "sem_dados", "nao_aplicavel"]
    registros: int = 0
    note: str | None = None
    canonical_path: str | None = None


class DptCompanyProfile(BaseModel):
    id: str
    nome: str
    status: str
    cidade: str | None = None
    estado: str | None = None
    generated_at: datetime
    health: list[DptHealthArea] = Field(default_factory=list)
    twin: list[DptTwinDimension] = Field(default_factory=list)
    areas_com_casos: list[str] = Field(default_factory=list)
    casos_abertos: int = 0
    prazos_pendentes: int = 0
    documentos: int = 0
    sociedades: int = 0
    operacoes_lgpd: int = 0
    operacoes_lgpd_alto_risco: int = 0
    autos_ambientais: int = 0
    notes: list[str] = Field(default_factory=list)


class DptActionRequest(BaseModel):
    action: Literal["conselho", "preflight", "diagnostico"]
    client_id: str
    question: str = Field(min_length=3, max_length=12000)
    area: str | None = Field(default=None, max_length=80)


class DptActionResponse(BaseModel):
    action: Literal["conselho", "preflight", "diagnostico"]
    client_id: str
    conteudo: str
    estruturado: dict[str, Any] | None = None
    fontes: list[dict[str, Any]] = Field(default_factory=list)
    citacoes: list[Any] = Field(default_factory=list)
    alertas: list[str] = Field(default_factory=list)
    critica_adversarial: dict[str, Any] | None = None
    is_rascunho: bool = True
    requer_revisao: bool = True
    status_hitl: str
    aviso_hitl: str
    log_id: str | None = None
