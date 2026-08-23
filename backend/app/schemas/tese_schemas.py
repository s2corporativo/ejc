# ── app/schemas/tese_schemas.py ─────────────────────────────────────
# Schemas Pydantic para Teses Jurídicas (request/response).
from __future__ import annotations
from typing import Optional
from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel, Field

from app.models.tese_juridica import TipoTese, StatusTese


class TaxonomiaBase(BaseModel):
    area: str = Field(..., min_length=1, max_length=100)
    subarea: str = Field(..., min_length=1, max_length=100)
    tema: str = Field(..., min_length=1, max_length=150)
    subtema: Optional[str] = Field(None, max_length=150)
    descricao: Optional[str] = None
    ativo: bool = True


class TaxonomiaCreate(TaxonomiaBase):
    pass


class TaxonomiaResponse(TaxonomiaBase):
    id: UUID
    nivel: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FundamentacaoLegalBase(BaseModel):
    norma: str = Field(..., max_length=50)
    artigo: Optional[str] = None
    paragrafo: Optional[str] = None
    inciso: Optional[str] = None
    alinea: Optional[str] = None
    texto_relevante: Optional[str] = None
    interpretacao: Optional[str] = None
    tipo: Optional[str] = None


class FundamentacaoLegalCreate(FundamentacaoLegalBase):
    pass


class FundamentacaoLegalResponse(FundamentacaoLegalBase):
    id: UUID
    tese_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class PrecedenteBase(BaseModel):
    tribunal: str = Field(..., max_length=120)
    orgao_julgador: Optional[str] = None
    classe: Optional[str] = None
    numero: Optional[str] = None
    relator: Optional[str] = None
    data_julgamento: Optional[date] = None
    data_publicacao: Optional[date] = None
    ementa: Optional[str] = None
    ementa_resumida: Optional[str] = None
    tipo_relacao: str = Field(default="favoravel", max_length=50)
    vinculante: bool = False
    fonte_url: Optional[str] = None
    fonte: Optional[str] = None


class PrecedenteCreate(PrecedenteBase):
    pass


class PrecedenteResponse(PrecedenteBase):
    id: UUID
    tese_id: UUID
    vezes_citada: int
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProcessoVitoriososBase(BaseModel):
    tribunal: Optional[str] = None
    classe: Optional[str] = None
    numero: Optional[str] = None
    resultado: Optional[str] = None
    contexto: Optional[str] = None
    data_decisao: Optional[date] = None
    url: Optional[str] = None
    fonte: Optional[str] = None


class ProcessoVitoriososCreate(ProcessoVitoriososBase):
    pass


class ProcessoVitoriososResponse(ProcessoVitoriososBase):
    id: UUID
    tese_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class TeseJuridicaBase(BaseModel):
    titulo: str = Field(..., min_length=5, max_length=300)
    sumario: Optional[str] = None
    tipo: TipoTese
    parte_favorecida: Optional[str] = None
    procedimento: Optional[str] = None
    instancia: Optional[str] = None
    tese_texto: str = Field(..., min_length=10)
    argumento: Optional[str] = None
    pressupostos: Optional[str] = None
    excecoes: Optional[str] = None
    estrategia: Optional[str] = None
    score: int = Field(default=50, ge=0, le=100)


class TeseJuridicaCreate(TeseJuridicaBase):
    taxonomia_id: UUID
    fundamentacoes: Optional[list[FundamentacaoLegalCreate]] = None
    precedentes: Optional[list[PrecedenteCreate]] = None


class TeseJuridicaUpdate(BaseModel):
    titulo: Optional[str] = None
    sumario: Optional[str] = None
    tipo: Optional[TipoTese] = None
    tese_texto: Optional[str] = None
    argumento: Optional[str] = None
    pressupostos: Optional[str] = None
    excecoes: Optional[str] = None
    estrategia: Optional[str] = None
    score: Optional[int] = Field(None, ge=0, le=100)
    status: Optional[StatusTese] = None


class TeseJuridicaResponse(TeseJuridicaBase):
    id: UUID
    taxonomia_id: UUID
    status: StatusTese
    versao: int
    score_calculos: Optional[dict] = None
    decisoes_favoraveis: int
    decisoes_desfavoraveis: int
    decisoes_parciais: int
    taxa_sucesso: Optional[float] = None
    data_revisao: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TeseJuridicaDetalhesResponse(TeseJuridicaResponse):
    """Resposta detalhada com fundamentações, precedentes e processos relacionados."""
    fundamentacoes: list[FundamentacaoLegalResponse] = []
    precedentes: list[PrecedenteResponse] = []
    processos_vitoriosos: list[ProcessoVitoriososResponse] = []


class AnaliseTeseRequest(BaseModel):
    """Request para análise de um caso — retorna teses aplicáveis."""
    texto_caso: str = Field(..., min_length=20)
    documento_id: Optional[UUID] = None
    processo_id: Optional[UUID] = None
    areas_interesse: Optional[list[str]] = None  # Ex.: ["Consumidor", "Bancário"]
    apenas_ataque: bool = False
    apenas_defesa: bool = False
    limite_teses: int = Field(default=10, ge=1, le=50)


class AnaliseTeseResponse(BaseModel):
    """Resposta de análise — teses recomendadas com precedentes e provas."""
    questao_juridica: str  # Questão extraída do caso
    teses_ataque: list[TeseJuridicaResponse] = []
    teses_defesa: list[TeseJuridicaResponse] = []
    contrateses: list[TeseJuridicaResponse] = []
    precedentes_favoraveis: list[PrecedenteResponse] = []
    precedentes_contrarios: list[PrecedenteResponse] = []
    legislacao_aplicavel: list[FundamentacaoLegalResponse] = []
    provas_necessarias: list[str] = []
    riscos: list[str] = []
    confianca: float = Field(..., ge=0.0, le=1.0)  # Nível de confiança da análise
