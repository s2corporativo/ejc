from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


Competencia = str


class DespesaBase(BaseModel):
    categoria: str = Field(min_length=1, max_length=80)
    subcategoria: str | None = Field(default=None, max_length=80)
    tipo: Literal["fixo", "variavel"] = "fixo"
    descricao: str = Field(min_length=1, max_length=2000)
    valor: Decimal = Field(ge=Decimal("0"), max_digits=14, decimal_places=2)
    vencimento: date | None = None
    pago_em: date | None = None
    recorrente: bool = False
    recorrencia: str | None = Field(default=None, max_length=40)
    status: Literal["pendente", "pago", "cancelado"] = "pendente"
    competencia: Competencia | None = None

    @field_validator("categoria", "descricao")
    @classmethod
    def _trim_obrigatorio(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("campo não pode ser vazio")
        return value

    @field_validator("subcategoria", "recorrencia")
    @classmethod
    def _trim_opcional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("competencia")
    @classmethod
    def _competencia_valida(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if len(value) != 7 or value[4] != "-":
            raise ValueError("competência deve usar o formato AAAA-MM")
        try:
            ano, mes = (int(p) for p in value.split("-", 1))
        except ValueError as exc:
            raise ValueError("competência deve usar o formato AAAA-MM") from exc
        if ano < 2000 or not 1 <= mes <= 12:
            raise ValueError("competência inválida")
        return f"{ano:04d}-{mes:02d}"

    @model_validator(mode="after")
    def _coerencia(self):
        if self.status == "pago" and self.pago_em is None:
            # Data de pagamento pode ser preenchida pelo fluxo de baixa, mas o
            # CRUD não inventa uma data retroativa. Mantém o estado explícito.
            pass
        if self.recorrente and not self.recorrencia:
            self.recorrencia = "mensal"
        if not self.recorrente:
            self.recorrencia = None
        return self


class DespesaCreate(DespesaBase):
    pass


class DespesaUpdate(BaseModel):
    categoria: str | None = Field(default=None, min_length=1, max_length=80)
    subcategoria: str | None = Field(default=None, max_length=80)
    tipo: Literal["fixo", "variavel"] | None = None
    descricao: str | None = Field(default=None, min_length=1, max_length=2000)
    valor: Decimal | None = Field(
        default=None, ge=Decimal("0"), max_digits=14, decimal_places=2
    )
    vencimento: date | None = None
    pago_em: date | None = None
    recorrente: bool | None = None
    recorrencia: str | None = Field(default=None, max_length=40)
    status: Literal["pendente", "pago", "cancelado"] | None = None
    competencia: Competencia | None = None

    @field_validator("competencia")
    @classmethod
    def _competencia_valida(cls, value: str | None) -> str | None:
        return DespesaBase._competencia_valida(value)

    @field_validator("categoria", "descricao")
    @classmethod
    def _trim_obrigatorio(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("campo não pode ser vazio")
        return value


class GerarRecorrentesRequest(BaseModel):
    competencia: Competencia

    @field_validator("competencia")
    @classmethod
    def _competencia_valida(cls, value: str) -> str:
        validado = DespesaBase._competencia_valida(value)
        assert validado is not None
        return validado
