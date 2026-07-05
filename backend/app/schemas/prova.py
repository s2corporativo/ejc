# ── app/schemas/prova.py ──────────────────────────────────────────────────────
# Schemas da Gestão de Provas por caso. `tipo` validado pelo enum TipoProva
# (domínio em código; coluna é VARCHAR).
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.models.prova import TipoProva


class ProvaCreate(BaseModel):
    titulo:        str = Field(min_length=1, max_length=255)
    tipo:          TipoProva = TipoProva.documental
    descricao:     Optional[str] = Field(None, max_length=5000)
    document_id:   Optional[str] = Field(None, max_length=36)
    tese_id:       Optional[str] = Field(None, max_length=36)
    fato_probando: Optional[str] = Field(None, max_length=5000)
    ordem:         int = Field(0, ge=0)


class ProvaUpdate(BaseModel):
    titulo:        Optional[str] = Field(None, min_length=1, max_length=255)
    tipo:          Optional[TipoProva] = None
    descricao:     Optional[str] = Field(None, max_length=5000)
    document_id:   Optional[str] = Field(None, max_length=36)
    tese_id:       Optional[str] = Field(None, max_length=36)
    fato_probando: Optional[str] = Field(None, max_length=5000)
    ordem:         Optional[int] = Field(None, ge=0)
