"""Contratos do agregador determinístico do leitor de autos.

A camada apenas consolida resultados já produzidos pelo intake documental. Ela
não interpreta o mérito, não consulta LLM e não cria prazo ou peça processual.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.document_intake import DocumentoIntakeResult


class FonteDocumentoAutos(BaseModel):
    documento_id: str = Field(..., min_length=1, max_length=64)
    nome_arquivo: str | None = Field(default=None, max_length=500)
    pagina: int | None = Field(default=None, ge=1)
    status_fonte: str | None = Field(default=None, max_length=50)
    processo_origem: str | None = Field(default=None, max_length=100)
    data_documento: str | None = Field(default=None, max_length=40)
    hash_conteudo: str | None = Field(default=None, max_length=128)


class DocumentoAutosEntrada(BaseModel):
    ordem: int = Field(..., ge=1)
    fonte: FonteDocumentoAutos
    intake: DocumentoIntakeResult
    parcial: bool = False
    caracteres_lidos: int | None = Field(default=None, ge=0)


class ReferenciaAutos(BaseModel):
    documento_id: str
    nome_arquivo: str | None = None
    pagina: int | None = None
    trecho_origem: str | None = None
    confianca: float | None = Field(default=None, ge=0, le=1)
    status_fonte: str | None = None


class DocumentoIndiceAutos(BaseModel):
    ordem: int
    documento_id: str
    nome_arquivo: str | None = None
    tipo_documento: str | None = None
    resumo: str | None = None
    data_documento: str | None = None
    processo_origem: str | None = None
    status_fonte: str | None = None
    parcial: bool = False
    necessita_revisao_humana: bool = True


class ParteAutos(BaseModel):
    nome: str
    papeis: list[str] = Field(default_factory=list)
    fontes: list[ReferenciaAutos] = Field(default_factory=list)


class ItemTextoAutos(BaseModel):
    texto: str
    fontes: list[ReferenciaAutos] = Field(default_factory=list)


class PrazoAutos(BaseModel):
    tipo: str | None = None
    data_base: str | None = None
    termo_final: str
    fatal: bool = False
    base_legal: str | None = None
    fontes: list[ReferenciaAutos] = Field(default_factory=list)


class EventoAutos(BaseModel):
    data: str
    tipo: str
    descricao: str
    documento_id: str
    nome_arquivo: str | None = None
    pagina: int | None = None
    status_fonte: str | None = None


class LacunaAutos(BaseModel):
    descricao: str
    campo_alvo: str | None = None
    severidade: str | None = None
    documento_id: str | None = None
    nome_arquivo: str | None = None


class EstatisticasAutos(BaseModel):
    documentos: int = 0
    partes: int = 0
    pedidos: int = 0
    provas: int = 0
    prazos_explicitos: int = 0
    riscos: int = 0
    teses: int = 0
    lacunas: int = 0


class LeitorAutosResultado(BaseModel):
    indice: list[DocumentoIndiceAutos] = Field(default_factory=list)
    partes: list[ParteAutos] = Field(default_factory=list)
    fatos: list[ItemTextoAutos] = Field(default_factory=list)
    pedidos: list[ItemTextoAutos] = Field(default_factory=list)
    provas: list[ItemTextoAutos] = Field(default_factory=list)
    prazos: list[PrazoAutos] = Field(default_factory=list)
    cronologia: list[EventoAutos] = Field(default_factory=list)
    riscos: list[ItemTextoAutos] = Field(default_factory=list)
    teses: list[ItemTextoAutos] = Field(default_factory=list)
    lacunas: list[LacunaAutos] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
    necessita_revisao_humana: bool = True
    estatisticas: EstatisticasAutos = Field(default_factory=EstatisticasAutos)
