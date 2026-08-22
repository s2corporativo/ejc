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

# Um PAGAMENTO, ao contrário do honorário, não pode ser zero nem negativo:
# `ge=0` deixaria passar lançamento de R$ 0,00, que não é pagamento. Estorno
# tem natureza contábil própria e não pode entrar disfarçado de pagamento
# negativo — quando existir, entra por caminho próprio, com trilha própria.
ValorPagamento = condecimal(gt=0)


class FeePaymentCreate(BaseModel):
    """Pagamento de honorário — o único ponto que altera o quanto foi recebido.

    `valor: Decimal` sem restrição alguma (auditoria de 22/08/2026) permitia
    duas coisas que fazem o financeiro mentir:

    1. **Pagamento negativo.** Sequência reproduzida contra o backend com
       Postgres real: honorário de R$ 1.000,00 → pagamento de +1.000,00
       (`status` vira `pago`, correto) → pagamento de −1.000,00, aceito com
       HTTP 201. A soma real de `fee_payments` volta a R$ 0,00, mas o `status`
       do honorário **continua `pago`** — o router só promove a `pago` quando a
       soma alcança o valor, e nunca reavalia para baixo. Resultado: honorário
       integralmente em aberto exibido como quitado, invisível na cobrança.
    2. **Erro de digitação silencioso.** O campo é `forma`; um cliente que
       enviasse `forma_pagamento` tinha o campo descartado pelo Pydantic e
       gravava o pagamento com `forma = NULL`, sem qualquer aviso — mesma
       classe de defeito do honorário sem valor. `extra="forbid"` faz o erro
       falhar alto. O frontend (`pages/Honorarios.tsx`) já envia exatamente
       `{valor, data_pagamento, forma}`, então nada em uso é recusado.

    A regra "valores monetários nunca negativos" já existia neste arquivo para
    `fees.valor` (`ValorNaoNegativo`, auditoria 2026-06-30/M5); o pagamento
    apenas não fora alcançado por ela.
    """

    model_config = ConfigDict(extra="forbid")

    valor: ValorPagamento
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
