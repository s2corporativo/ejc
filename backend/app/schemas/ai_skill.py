from __future__ import annotations
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class SkillListItem(BaseModel):
    id: str
    name: str
    display_name: str
    description: Optional[str]
    engine: str
    area: str
    functional_group: Literal["analisar", "produzir", "revisar", "preparar"]
    requires_case: bool
    requires_human_review: bool
    oab_restricted: bool

    model_config = {"from_attributes": True}


class SkillExecuteRequest(BaseModel):
    skill_name: str = Field(..., description="Nome da skill (campo 'name')")
    query: str = Field(..., min_length=5, max_length=12000)
    case_id: Optional[str] = Field(None)
    usar_rag: bool = Field(True)
    surface: Optional[str] = Field(None, max_length=60)
    area: Optional[str] = Field(None, max_length=80)
    phase: Optional[str] = Field(None, max_length=80)


class SkillExecuteResponse(BaseModel):
    conteudo: str
    skill: str
    skill_name: Optional[str] = None
    engine: str
    is_rascunho: bool = True
    requer_revisao: bool = True
    tokens_usados: int = 0
    custo_estimado_brl: float = 0.0
    processamento: Optional[dict[str, Any]] = None
    transcricao: Optional[str] = None
    ai_log_id: Optional[str] = None
    classificacao: Optional[dict[str, Any]] = None
    proximas_acoes: list[dict[str, Any]] = Field(default_factory=list)
    auditoria: Optional[dict[str, Any]] = None
    aviso_privacidade: Optional[str] = None
    aviso: str = "RASCUNHO — revisão humana obrigatória antes de qualquer uso (OAB)."


class ContextualActionItem(BaseModel):
    id: str
    name: str
    display_name: str
    description: Optional[str] = None
    area: str
    functional_group: Literal["analisar", "produzir", "revisar", "preparar"]
    requires_case: bool
    requires_human_review: bool
    oab_restricted: bool
    reason: str
    score: int


class ContextualActionsResponse(BaseModel):
    surface: str
    area: Optional[str] = None
    phase: Optional[str] = None
    document_type: Optional[str] = None
    case_id: Optional[str] = None
    actions: list[ContextualActionItem]
    total_catalog: int
    selection_method: str = "contextual_rules_v1"
