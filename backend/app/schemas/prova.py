# ── app/schemas/prova.py ──────────────────────────────────────────────────────
# Schemas da Gestão de Provas por caso. `tipo` validado pelo enum TipoProva
# (domínio em código; coluna é VARCHAR).
from __future__ import annotations

from typing import Literal, Optional

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


class SugestaoProvaFaltante(BaseModel):
    """Uma prova FALTANTE sugerida pela IA (Mapa Probatório — Etapa 6).

    É SUGESTÃO/rascunho (HITL): o advogado que acatar cria a Prova pelo fluxo
    normal. Validação estrita aqui é a última linha do parse defensivo — item
    que não couber no schema é descartado, nunca propagado ao frontend.
    """
    titulo:          str = Field(min_length=1, max_length=255)
    por_que_importa: str = Field("", max_length=2000)
    como_obter:      str = Field("", max_length=2000)
    criticidade:     Literal["alta", "media", "baixa"] = "media"


class ProvaUpdate(BaseModel):
    titulo:        Optional[str] = Field(None, min_length=1, max_length=255)
    tipo:          Optional[TipoProva] = None
    descricao:     Optional[str] = Field(None, max_length=5000)
    document_id:   Optional[str] = Field(None, max_length=36)
    tese_id:       Optional[str] = Field(None, max_length=36)
    fato_probando: Optional[str] = Field(None, max_length=5000)
    ordem:         Optional[int] = Field(None, ge=0)
