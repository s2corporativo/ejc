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
# Tipos em que `percentual_exito` é REALMENTE aplicado no cálculo — ver
# `routers/honorarios_oab.py`: `elif f.tipo in (FeeTipo.exito, FeeTipo.misto)
# and f.percentual_exito and proveito`. Nos demais o campo seria gravado e
# ignorado, que é a mesma classe de defeito do honorário sem valor: o registro
# diz uma coisa e o sistema faz outra.
_TIPOS_COM_PERCENTUAL = frozenset({FeeTipo.exito.value, FeeTipo.misto.value})


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
        # Percentual só vale onde o cálculo o aplica. Aceitar
        # `{tipo: 'fixo', percentual_exito: 20}` gravava um honorário sem valor
        # fixo cujo percentual `honorarios_oab.py` nunca lê — cobrança que
        # existe no cadastro e não existe no cálculo. Achado da 2ª revisão do
        # Codex no PR #1238.
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
    """Alteração parcial de honorário.

    Mantém a mesma regra monetária da criação: `valor` nunca pode ser negativo.
    Campos desconhecidos falham com 422 para evitar atualizações silenciosamente
    ignoradas em uma superfície financeira.
    """

    model_config = ConfigDict(extra="forbid")

    descricao: Optional[str] = None
    valor: Optional[ValorNaoNegativo] = None
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

    # `extra="forbid"` é o contrato declarado (aparece no OpenAPI); a mensagem
    # que o advogado lê vem do validador abaixo.
    model_config = ConfigDict(extra="forbid")

    valor: Decimal
    data_pagamento: date
    forma: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _recusar_campo_desconhecido(cls, dados):
        """Nomeia o campo errado em português, em vez de "Extra inputs are not
        permitted" — que não diz QUAL campo nem o que fazer.

        Roda antes da validação de campos, então é esta mensagem que chega ao
        toast do frontend (`components/Toast.tsx` extrai `msg` de cada item do
        array de erro do Pydantic).
        """
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
        """Mensagem em português, como no resto do repositório (`case.py`).

        `condecimal(gt=0)` faria a mesma recusa, mas com "Input should be
        greater than 0" — inglês, num sistema cujo padrão é o português.
        """
        if v <= 0:
            raise ValueError(
                "valor do pagamento deve ser maior que zero "
                "(R$ 0,00 não é pagamento; estorno tem lançamento próprio)"
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
