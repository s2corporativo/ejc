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
    with pytest.raises(ValidationError) as ei:
        FeePaymentCreate(valor="-1000.00", data_pagamento=HOJE, forma="pix")
    assert "maior que zero" in str(ei.value)


def test_pagamento_zerado_e_recusado():
    """R$ 0,00 não é pagamento — `ge=0` deixaria passar; a regra é > 0."""
    with pytest.raises(ValidationError):
        FeePaymentCreate(valor="0", data_pagamento=HOJE, forma="pix")


def test_campo_com_nome_errado_e_recusado_em_vez_de_descartado():
    """O schema espera `forma`; `forma_pagamento` gravava `forma = NULL`.

    Antes, o Pydantic descartava o campo desconhecido em silêncio e o
    pagamento entrava sem forma de pagamento, com HTTP 201.
    """
    with pytest.raises(ValidationError) as ei:
        FeePaymentCreate(
            valor="100.00", data_pagamento=HOJE, forma_pagamento="boleto"
        )
    assert "forma_pagamento" in str(ei.value)


def test_mensagens_de_erro_saem_em_portugues_e_nomeiam_o_problema():
    """O que o advogado lê no toast é a `msg` de cada erro do Pydantic.

    Sem os validadores próprios, as recusas chegariam como "Input should be
    greater than 0" e "Extra inputs are not permitted" — inglês, e a segunda
    sem dizer QUAL campo está errado. O repositório escreve suas validações em
    português (ver `schemas/case.py`), e é isso que o frontend exibe:
    `components/Toast.tsx` achata o array de erro extraindo `msg` de cada item.
    """
    with pytest.raises(ValidationError) as ei:
        FeePaymentCreate(valor="0", data_pagamento=HOJE)
    msgs = " ".join(e["msg"] for e in ei.value.errors())
    assert "maior que zero" in msgs
    assert "Input should be" not in msgs

    with pytest.raises(ValidationError) as ei:
        FeePaymentCreate(valor="10", data_pagamento=HOJE, valor_pago="10")
    msgs = " ".join(e["msg"] for e in ei.value.errors())
    assert "valor_pago" in msgs, "a mensagem precisa nomear o campo errado"
    assert "Extra inputs are not permitted" not in msgs


def test_pagamento_valido_e_aceito():
    p = FeePaymentCreate(valor="1500.50", data_pagamento=HOJE, forma="pix")
    assert p.valor == pytest.approx(1500.50)
    assert p.forma == "pix"


def test_forma_e_opcional():
    """Nem todo lançamento traz a forma; o que não pode é vir com nome errado."""
    p = FeePaymentCreate(valor="10.00", data_pagamento=HOJE)
    assert p.forma is None
