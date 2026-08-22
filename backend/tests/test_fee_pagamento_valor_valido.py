# -*- coding: utf-8 -*-
"""Pagamento de honorário exige valor positivo e recusa campo desconhecido.

Regressão da auditoria funcional de 22/08/2026 (Issue #1237). `FeePaymentCreate`
declarava `valor: Decimal` — sem restrição nenhuma — enquanto `fees.valor` já
era `condecimal(ge=0)` desde a auditoria de 2026-06-30 (M5). O pagamento
simplesmente não fora alcançado pela regra.

Sequência reproduzida contra o backend com Postgres real, todas as respostas
HTTP 201:

    honorário R$ 1.000,00
    → pagamento +1.000,00   soma = 1.000,00, status = "pago"   (correto)
    → pagamento −1.000,00   soma =     0,00, status = "pago"   (mentira)

`registrar_pagamento` só promove o honorário a `pago` quando a soma alcança o
valor contratado; nunca reavalia para baixo. Um lançamento negativo devolve a
dívida ao zero e deixa o registro exibido como quitado — o honorário some da
cobrança sem nunca ter sido recebido.
"""
from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.fee import FeePaymentCreate

HOJE = date.today()


def test_pagamento_negativo_e_recusado():
    """O caso que zerava o recebido mantendo o honorário como `pago`."""
    with pytest.raises(ValidationError):
        FeePaymentCreate(valor="-1000.00", data_pagamento=HOJE, forma="pix")


def test_pagamento_zerado_e_recusado():
    """R$ 0,00 não é pagamento — `ge=0` deixaria passar; a regra é `gt=0`."""
    with pytest.raises(ValidationError):
        FeePaymentCreate(valor="0", data_pagamento=HOJE, forma="pix")


def test_campo_com_nome_errado_e_recusado_em_vez_de_descartado():
    """O schema espera `forma`; `forma_pagamento` gravava `forma = NULL`.

    Antes, o Pydantic descartava o campo desconhecido em silêncio e o
    pagamento entrava sem forma de pagamento, com HTTP 201.
    """
    with pytest.raises(ValidationError):
        FeePaymentCreate(
            valor="100.00", data_pagamento=HOJE, forma_pagamento="boleto"
        )


def test_pagamento_valido_e_aceito():
    p = FeePaymentCreate(valor="1500.50", data_pagamento=HOJE, forma="pix")
    assert p.valor == pytest.approx(1500.50)
    assert p.forma == "pix"


def test_forma_e_opcional():
    """Nem todo lançamento traz a forma; o que não pode é vir com nome errado."""
    p = FeePaymentCreate(valor="10.00", data_pagamento=HOJE)
    assert p.forma is None
