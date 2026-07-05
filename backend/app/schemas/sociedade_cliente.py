# ── app/schemas/sociedade_cliente.py ─────────────────────────────────────────
# Schemas da gestão societária de CLIENTES (vertical Empresarial).
# O documento do sócio entra opcional no create/update e NUNCA volta em claro:
# as respostas expõem apenas `documento_mascarado`.
from __future__ import annotations

from decimal import Decimal
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.models.sociedade_cliente import TipoSocietario, TipoEventoSocietario


class SociedadeCreate(BaseModel):
    client_id:       str
    razao_social:    str = Field(min_length=2, max_length=255)
    tipo_societario: TipoSocietario
    cnpj:            Optional[str] = Field(None, max_length=18)
    capital_social:  Optional[Decimal] = Field(None, ge=0)


class SociedadeUpdate(BaseModel):
    razao_social:    Optional[str] = Field(None, min_length=2, max_length=255)
    tipo_societario: Optional[TipoSocietario] = None
    cnpj:            Optional[str] = Field(None, max_length=18)
    capital_social:  Optional[Decimal] = Field(None, ge=0)


class SocioCreate(BaseModel):
    nome:          str = Field(min_length=2, max_length=255)
    documento:     Optional[str] = Field(None, max_length=20,
                                         description="CPF/CNPJ — cifrado em repouso; nunca retorna em claro")
    quotas:        Decimal = Field(ge=0)
    pro_labore:    Optional[Decimal] = Field(None, ge=0)
    administrador: bool = False


class SocioUpdate(BaseModel):
    nome:          Optional[str] = Field(None, min_length=2, max_length=255)
    documento:     Optional[str] = Field(None, max_length=20)
    quotas:        Optional[Decimal] = Field(None, ge=0)
    pro_labore:    Optional[Decimal] = Field(None, ge=0)
    administrador: Optional[bool] = None


class EventoCreate(BaseModel):
    tipo:        TipoEventoSocietario
    descricao:   Optional[str] = Field(None, max_length=2000)
    data_evento: date

    @field_validator("data_evento")
    @classmethod
    def _data_nao_futura_demais(cls, v: date) -> date:
        # Sanidade: evento societário não pode ser registrado mais de 1 ano no
        # futuro (protege contra typo de ano). Passado é livre (histórico).
        if v.year > date.today().year + 1:
            raise ValueError("data_evento muito no futuro — confira o ano")
        return v
