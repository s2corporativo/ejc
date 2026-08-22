# ── app/schemas/fee.py ───────────────────────────────────────────────────────
from __future__ import annotations
from pydantic import BaseModel, condecimal, field_validator, model_validator
from typing import Optional
from datetime import date, datetime
from decimal import Decimal

from app.models.fee import FeeTipo, FeeStatus

# Valores monetários nunca negativos (auditoria 2026-06-30, M5).
ValorNaoNegativo = condecimal(ge=0)
PercentualNaoNegativo = condecimal(ge=0, le=100)

# Fonte única de verdade: os valores aceitos em `tipo` na CRIAÇÃO são os da enum
# FeeTipo (inclui 'sucumbencia' desde a migration 097). Mantemos o campo como
# `str` — o router faz Fee(**payload.model_dump()) e a coluna é SAEnum(FeeTipo),
# que aceita a string — logo a validação não muda o fluxo de dados, apenas
# rejeita valores fora do domínio (evita 500/erro de enum no banco).
_TIPOS_FEE_VALIDOS = frozenset(t.value for t in FeeTipo)
# Idem para `status` na ATUALIZAÇÃO: coluna SAEnum(FeeStatus), setattr direto no
# UPDATE → string fora do domínio estourava no asyncpg (500) em vez de 422.
_STATUS_FEE_VALIDOS = frozenset(s.value for s in FeeStatus)

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
        """Honorário precisa dizer QUANTO se cobra — em reais ou em percentual.

        Ambos eram opcionais: `POST /fees/` respondia 201 para um corpo só com
        `descricao` e `client_id`, gravando `fees.valor = NULL`. O registro
        entra na listagem, conta como "pendente" e não soma em lugar nenhum —
        cobrança que nunca será feita porque não há quanto cobrar. Pior no
        caminho silencioso: um campo com nome errado no cliente (ex.:
        `valor_total` em vez de `valor`) é descartado pelo Pydantic e vira o
        mesmo registro vazio, com HTTP 201.

        Exigir ao menos um dos dois não fecha nenhum caso legítimo: honorário
        fixo/contratual tem `valor`; honorário de êxito tem `percentual_exito`
        (e pode ter os dois). Ajuste de valor posterior segue livre pelo
        `FeeUpdate`, que é parcial por natureza.
        """
        if self.valor is None and self.percentual_exito is None:
            raise ValueError(
                "honorário exige 'valor' (R$) ou 'percentual_exito' (%). "
                "Sem um dos dois o registro nasce sem quanto cobrar e não "
                "entra em nenhum somatório financeiro."
            )
        return self


class FeeUpdate(BaseModel):
    descricao: Optional[str] = None
    valor: Optional[Decimal] = None
    status: Optional[str] = None
    data_vencimento: Optional[date] = None
    observacoes: Optional[str] = None

    @field_validator("status")
    @classmethod
    def _validar_status(cls, v: Optional[str]) -> Optional[str]:
        # Vazio/None PASSA (update parcial); valor fora do enum → 422, não 500.
        if v is None or str(v).strip() == "":
            return v
        if v not in _STATUS_FEE_VALIDOS:
            raise ValueError(
                "status de honorário inválido: "
                f"{v!r}. Valores permitidos: {sorted(_STATUS_FEE_VALIDOS)}"
            )
        return v

class FeePaymentCreate(BaseModel):
    valor: Decimal
    data_pagamento: date
    forma: Optional[str] = None

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
