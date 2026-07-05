# ── app/schemas/redesign.py ──────────────────────────────────────────────────
# Schemas das tabelas de configuração do redesign (migração 057):
#   ModuleHelp (ajuda contextual) e AreaModuloMapping (matriz área → módulos).
from __future__ import annotations
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ── Module Help (F4/R1 — botão "?" por tela) ─────────────────────────────────

class ModuleHelpCreate(BaseModel):
    module_key:  str = Field(min_length=2, max_length=60,
                             description='Rota do frontend sem barra inicial (ex.: "casos", "ramos/civel")')
    titulo:      str = Field(min_length=3, max_length=200)
    conteudo_md: str = Field(min_length=1, description="Markdown: o que faz, quando usar, passo a passo")
    ordem:       int = 0
    ativo:       bool = True

    @field_validator("module_key")
    @classmethod
    def _normaliza_module_key(cls, v: str) -> str:
        return v.strip().strip("/").lower()


class ModuleHelpUpdate(BaseModel):
    module_key:  Optional[str] = Field(None, min_length=2, max_length=60)
    titulo:      Optional[str] = Field(None, min_length=3, max_length=200)
    conteudo_md: Optional[str] = Field(None, min_length=1)
    ordem:       Optional[int] = None
    ativo:       Optional[bool] = None

    @field_validator("module_key")
    @classmethod
    def _normaliza_module_key(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().strip("/").lower() if v else v


# ── Matriz área do direito → módulos/ferramentas (R6) ────────────────────────

class FerramentaItem(BaseModel):
    nome:     str = Field(min_length=1, max_length=120)
    endpoint: str = Field(min_length=1, max_length=200,
                          description='Endpoint REAL relativo a /api (ex.: "/civel/ferramentas/prazos-contestacao")')


class AreaModuloCreate(BaseModel):
    area_juridica:         str = Field(min_length=2, max_length=50,
                                       description='Slug minúsculo (ex.: "civel", "familia", "administrativo")')
    module_key:            str = Field(min_length=2, max_length=60)
    habilitado:            bool = True
    ordem:                 int = 0
    ferramentas:           Optional[list[FerramentaItem]] = None
    workflow_template_id:  Optional[str] = None
    checklist_template_id: Optional[str] = None

    @field_validator("area_juridica", "module_key")
    @classmethod
    def _normaliza_slug(cls, v: str) -> str:
        return v.strip().strip("/").lower()


class AreaModuloUpdate(BaseModel):
    area_juridica:         Optional[str] = Field(None, min_length=2, max_length=50)
    module_key:            Optional[str] = Field(None, min_length=2, max_length=60)
    habilitado:            Optional[bool] = None
    ordem:                 Optional[int] = None
    ferramentas:           Optional[list[FerramentaItem]] = None
    workflow_template_id:  Optional[str] = None
    checklist_template_id: Optional[str] = None

    @field_validator("area_juridica", "module_key")
    @classmethod
    def _normaliza_slug(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().strip("/").lower() if v else v


# ── Conversão extrajudicial → judicial (R8 — checklist bloqueante) ───────────
# Usados por app/routers/conversao_caso.py:
#   GET  /cases/{case_id}/converter-judicial/checklist  → ConversaoChecklistResponse
#   POST /cases/{case_id}/converter-judicial            → 422 c/ pendentes se pronto=false

class ConversaoChecklistItem(BaseModel):
    key:     str = Field(description="Identificador estável da verificação (ex.: 'procuracao_valida')")
    titulo:  str
    ok:      bool
    detalhe: str


class ConversaoChecklistResponse(BaseModel):
    itens:  list[ConversaoChecklistItem]
    pronto: bool = Field(description="True somente se TODAS as verificações estão ok")
