"""Schemas — governança de Teses (pinned, fluxo de aprovação, fork, versões).

Estende o router ``/teses`` existente com endpoints de governança. Mantém
compatibilidade com ``TeseIn``/``TeseOut`` legados — só adiciona campos novos.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field

from app.models.tese import TeseStatus


class TeseGovernancaUpdate(BaseModel):
    """PATCH parcial de campos de governança. Não toca em descricao/fundamentacao."""
    pinned: Optional[bool] = None
    experiencia_minima: Optional[str] = Field(None, max_length=30)
    conteudo_estruturado: Optional[str] = None


class TeseSubmitReview(BaseModel):
    """Envia tese ativa/rascunho para revisão do sócio (status → rascunho
    + revisor_id=None). A tese só volta a entrar no prompt quando o sócio
    aprovar."""
    note: Optional[str] = Field(None, max_length=500)


class TeseApprove(BaseModel):
    """Sócio responsável carimba a tese — status='ativa' + revisor_id +
    revisao_em. A partir desse momento ela é elegível para injeção no prompt."""
    note: Optional[str] = Field(None, max_length=500)


class TeseForkIn(BaseModel):
    """Cria/upsert fork pessoal do advogado. Se ``conteudo`` vazio, copia o
    ``conteudo_estruturado`` da tese (ou descricao como fallback)."""
    conteudo: Optional[str] = None
    note: Optional[str] = Field(None, max_length=500)


class TeseForkOut(BaseModel):
    id: str
    tese_id: str
    user_id: str
    conteudo: str
    note: Optional[str] = None
    created_at: str
    updated_at: str
    model_config = {"from_attributes": True}


class TeseVersionOut(BaseModel):
    id: str
    tese_id: str
    conteudo: str
    version: int
    autor_id: Optional[str] = None
    note: Optional[str] = None
    created_at: str
    model_config = {"from_attributes": True}


class TeseGovernancaOut(BaseModel):
    """Resposta com os campos de governança."""
    id: str
    titulo: str
    status: TeseStatus
    pinned: bool
    experiencia_minima: str
    revisor_id: Optional[str] = None
    revisao_em: Optional[str] = None
    conteudo_estruturado: Optional[str] = None
    model_config = {"from_attributes": True}
