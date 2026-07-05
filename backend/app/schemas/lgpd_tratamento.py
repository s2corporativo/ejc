# ── app/schemas/lgpd_tratamento.py ────────────────────────────────────────────
# Schemas do ROPA (Registro de Operações de Tratamento — art. 37 LGPD).
# Field(max_length=...) em TODA string: o texto é renderizado pelo WeasyPrint no
# RIPD (síncrono/caro) — limites protegem contra DoS por payload gigante.
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.models.lgpd_tratamento import BaseLegal

# Limites de tamanho (também aplicados ao HTML do RIPD).
_TXT_CURTO = 255
_TXT = 4000


class RegistroCreate(BaseModel):
    client_id:                   str = Field(max_length=36)
    nome_operacao:               str = Field(min_length=2, max_length=_TXT_CURTO)
    finalidade:                  str = Field(min_length=2, max_length=_TXT)
    base_legal:                  BaseLegal
    categorias_dados:            str = Field(min_length=1, max_length=_TXT)
    categorias_titulares:        str = Field(min_length=1, max_length=_TXT)
    dados_sensiveis:             bool = False
    compartilhamento:            Optional[str] = Field(None, max_length=_TXT)
    transferencia_internacional: bool = False
    paises_transferencia:        Optional[str] = Field(None, max_length=_TXT)
    prazo_retencao:              str = Field(min_length=1, max_length=_TXT)
    medidas_seguranca:           str = Field(min_length=1, max_length=_TXT)


class RegistroUpdate(BaseModel):
    nome_operacao:               Optional[str] = Field(None, min_length=2, max_length=_TXT_CURTO)
    finalidade:                  Optional[str] = Field(None, min_length=2, max_length=_TXT)
    base_legal:                  Optional[BaseLegal] = None
    categorias_dados:            Optional[str] = Field(None, min_length=1, max_length=_TXT)
    categorias_titulares:        Optional[str] = Field(None, min_length=1, max_length=_TXT)
    dados_sensiveis:             Optional[bool] = None
    compartilhamento:            Optional[str] = Field(None, max_length=_TXT)
    transferencia_internacional: Optional[bool] = None
    paises_transferencia:        Optional[str] = Field(None, max_length=_TXT)
    prazo_retencao:              Optional[str] = Field(None, min_length=1, max_length=_TXT)
    medidas_seguranca:           Optional[str] = Field(None, min_length=1, max_length=_TXT)
