# ── app/schemas/fee.py ───────────────────────────────────────────────────────
from __future__ import annotations
from pydantic import BaseModel, ConfigDict, condecimal, field_validator, model_validator
from typing import Optional
from datetime import date, datetime
from decimal import Decimal

from app.models.fee import FeeTipo, FeeStatus

# Valores monetários nunca negativos (auditoria 2026-06-30, M5).
ValorNaoNegativo = condecimal(ge=0)
PercentualNaoNegativo = condecimal(ge=0, le=100)

_TIPOS_FEE_VALIDOS = frozenset(t.value for t in FeeTipo)
_STATUS_FEE_VALIDOS = frozenset(s.value for s in FeeStatus)
_TIPOS_COM_PERCENTUAL = frozenset({FeeTipo.exito.value, FeeTipo.misto.value})
_FORMAS_PAGAMENTO = frozenset(
    {"pix", "transferencia", "dinheiro", "cartao", "boleto", "outro"}
)


class FeeCreate(BaseModel):
    tipo: str = "fixo"
    descricao: str
    valor: Optional[ValorNaoNegativo] = None
    percentual_exito: Optional[PercentualNaoNegativo] = None
    data_vencimento: Optional[date] = None
    client_id: str
    case_id: Optional[str] = None
    observacoes: Optional[str] = None

    @field_validator("tipo")
    @classmethod
    def _validar_tipo(cls, v: str) -> str:
        if v not in _TIPOS_FEE_VALIDOS:
            raise ValueError(
                "tipo de honorário inválido: "
                f"{v!r}. Valores permitidos: {sorted(_TIPOS_FEE_VALIDOS)}"
            )
        return v

    @model_validator(mode="after")
    def _exigir_valor_ou_percentual(self):
        if self.valor is None and self.percentual_exito is None:
            raise ValueError(
                "honorário exige 'valor' (R$) ou 'percentual_exito' (%). "
                "Sem um dos dois o registro nasce sem quanto cobrar e não "
                "entra em nenhum somatório financeiro."
            )
        if (
            self.percentual_exito is not None
            and self.tipo not in _TIPOS_COM_PERCENTUAL
        ):
            raise ValueError(
                f"'percentual_exito' não se aplica a honorário do tipo "
                f"{self.tipo!r}: o cálculo só usa percentual em "
                f"{sorted(_TIPOS_COM_PERCENTUAL)}. Use 'valor' (R$) para este "
                f"tipo, ou mude o tipo para 'exito'/'misto'."
            )
        return self


class FeeUpdate(BaseModel):
    """Alteração parcial de honorário com validação monetária estrita."""

    model_config = ConfigDict(extra="forbid")

    descricao: Optional[str] = None
    valor: Optional[ValorNaoNegativo] = None
    status: Optional[str] = None
    data_vencimento: Optional[date] = None
    observacoes: Optional[str] = None

    @field_validator("status")
    @classmethod
    def _validar_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None or str(v).strip() == "":
            return v
        if v not in _STATUS_FEE_VALIDOS:
            raise ValueError(
                "status de honorário inválido: "
                f"{v!r}. Valores permitidos: {sorted(_STATUS_FEE_VALIDOS)}"
            )
        return v


class FeePaymentCreate(BaseModel):
    """Pagamento de honorário — único ponto de entrada de caixa do fee.

    O valor é estritamente positivo. Estorno não usa valor negativo enviado pelo
    cliente: ele exige fluxo próprio e auditável, para não transformar correção
    contábil em edição silenciosa do ledger.
    """

    model_config = ConfigDict(extra="forbid")

    valor: Decimal
    data_pagamento: date
    forma: Optional[str] = None
    comprovante_doc_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _recusar_campo_desconhecido(cls, dados):
        if isinstance(dados, dict):
            desconhecidos = sorted(set(dados) - set(cls.model_fields))
            if desconhecidos:
                raise ValueError(
                    f"campo(s) não reconhecido(s) em pagamento: "
                    f"{', '.join(desconhecidos)}. Use apenas: "
                    f"{', '.join(sorted(cls.model_fields))}."
                )
        return dados

    @field_validator("valor")
    @classmethod
    def _valor_positivo(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError(
                "valor do pagamento deve ser maior que zero "
                "(R$ 0,00 não é pagamento; estorno tem lançamento próprio)"
            )
        return v

    @field_validator("forma")
    @classmethod
    def _forma_controlada(cls, v: Optional[str]) -> Optional[str]:
        if v in (None, ""):
            return None
        if v not in _FORMAS_PAGAMENTO:
            raise ValueError(
                "forma de pagamento inválida. Valores permitidos: "
                + ", ".join(sorted(_FORMAS_PAGAMENTO))
            )
        return v


class FeeResponse(BaseModel):
    id: str
    tipo: str
    status: str
    descricao: str
    valor: Optional[Decimal] = None
    percentual_exito: Optional[Decimal] = None
    data_vencimento: Optional[date] = None
    data_pagamento: Optional[date] = None
    client_id: str
    case_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class FeeEstornoCreate(BaseModel):
    """Estorno de pagamento de honorário — lançamento próprio e auditável.

    Complementa a exigência dos guards de ``routers/fees.py`` ("registre
    eventual estorno em fluxo próprio"): nunca se edita nem se apaga um
    ``FeePayment``; o estorno é um lançamento novo, amarrado ao pagamento de
    origem, com motivo obrigatório e valor estritamente positivo e limitado
    ao saldo do pagamento original (a soma de estornos não pode superá-lo).
    """

    model_config = ConfigDict(extra="forbid")

    valor: Decimal
    data_estorno: date
    motivo: str

    @model_validator(mode="before")
    @classmethod
    def _recusar_campo_desconhecido(cls, dados):
        if isinstance(dados, dict):
            desconhecidos = sorted(set(dados) - set(cls.model_fields))
            if desconhecidos:
                raise ValueError(
                    f"campo(s) não reconhecido(s) em estorno: "
                    f"{', '.join(desconhecidos)}. Use apenas: "
                    f"{', '.join(sorted(cls.model_fields))}."
                )
        return dados

    @field_validator("valor")
    @classmethod
    def _valor_positivo(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError(
                "valor do estorno deve ser maior que zero "
                "(R$ 0,00 não é estorno; correção contábil não se faz "
                "com lançamento nulo)"
            )
        return v

    @field_validator("motivo")
    @classmethod
    def _motivo_obrigatorio(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError(
                "motivo do estorno é obrigatório: todo desmonte de caixa "
                "precisa ser rastreável a uma justificativa explícita"
            )
        return v.strip()


class FeeEstornoResponse(BaseModel):
    id: str
    fee_id: str
    fee_payment_id: str
    valor: Decimal
    motivo: str
    data_estorno: date
    created_at: datetime

    class Config:
        from_attributes = True
