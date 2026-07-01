from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class SkillListItem(BaseModel):
    id: str
    name: str
    display_name: str
    description: Optional[str]
    engine: str
    area: str
    requires_case: bool
    requires_human_review: bool
    oab_restricted: bool

    model_config = {"from_attributes": True}


class SkillExecuteRequest(BaseModel):
    skill_name: str = Field(..., description="Nome da skill (campo 'name')")
    query: str = Field(..., min_length=5, max_length=12000)
    case_id: Optional[str] = Field(None)
    usar_rag: bool = Field(False)


class SkillExecuteResponse(BaseModel):
    conteudo: str
    skill: str
    engine: str
    is_rascunho: bool = True
    requer_revisao: bool = True
    tokens_usados: int = 0
    custo_estimado_brl: float = 0.0
    aviso: str = "RASCUNHO — revisão humana obrigatória antes de qualquer uso (OAB)."
