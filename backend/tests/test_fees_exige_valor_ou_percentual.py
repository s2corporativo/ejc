# -*- coding: utf-8 -*-
"""`FeeCreate` exige dizer QUANTO se cobra — em reais ou em percentual.

Regressão da auditoria funcional de 22/08/2026 (Issue #1237). Contra o backend
local com Postgres real, `POST /api/fees/` devolvia **201** para um corpo só com
`descricao` e `client_id`, gravando `fees.valor = NULL`: honorário de êxito sem
valor e sem percentual, que aparece na listagem como pendente e não soma em
nenhum total. O caminho silencioso é pior — um campo com nome errado no cliente
(`valor_total` em vez de `valor`) é descartado pelo Pydantic e produz o mesmo
registro vazio, também com 201.
"""
from __future__ import annotations

import pytest
from decimal import Decimal
from pydantic import ValidationError

from app.schemas.fee import FeeCreate

BASE = {"descricao": "Honorário contratual", "client_id": "cliente-A"}


def test_sem_valor_e_sem_percentual_e_recusado():
    with pytest.raises(ValidationError) as ei:
        FeeCreate(**BASE, tipo="exito")
    assert "percentual_exito" in str(ei.value)


def test_campo_com_nome_errado_nao_vira_honorario_vazio():
    """`valor_total` não existe no schema; o Pydantic o descarta.

    Antes, o descarte silencioso produzia um honorário sem valor com HTTP 201.
    Agora a ausência de `valor`/`percentual_exito` é o que reprova — o erro de
    digitação passa a falhar alto, no lugar de virar registro vazio.
    """
    with pytest.raises(ValidationError):
        FeeCreate(**BASE, tipo="fixo", valor_total="5000.00")


def test_valor_em_reais_basta():
    f = FeeCreate(**BASE, tipo="fixo", valor="1500.00")
    assert f.valor is not None
    assert f.percentual_exito is None


def test_percentual_de_exito_basta():
    f = FeeCreate(**BASE, tipo="exito", percentual_exito="20")
    assert f.percentual_exito is not None
    assert f.valor is None


def test_os_dois_juntos_sao_aceitos():
    """Êxito com piso contratado: percentual + valor mínimo convivem."""
    f = FeeCreate(**BASE, tipo="exito", valor="1000.00", percentual_exito="15")
    assert f.valor is not None and f.percentual_exito is not None


def test_valor_zero_e_aceito_e_nao_confundido_com_ausencia():
    """`0` é uma decisão explícita (pro bono, cortesia); `None` é omissão.

    O validador não pode tratar zero como ausente — `condecimal(ge=0)` já
    admite zero, e um honorário zerado registrado de propósito é legítimo.
    """
    f = FeeCreate(**BASE, tipo="fixo", valor="0")
    assert f.valor == 0


def test_as_demais_validacoes_seguem_valendo():
    with pytest.raises(ValidationError):
        FeeCreate(**BASE, tipo="inexistente", valor="100")
    with pytest.raises(ValidationError):
        FeeCreate(**BASE, tipo="fixo", valor="-1")
    with pytest.raises(ValidationError):
        FeeCreate(**BASE, tipo="exito", percentual_exito="101")


# ── Percentual só onde o cálculo o aplica ───────────────────────────────────
# 2ª revisão do Codex no PR #1238. Com o campo novo no formulário e o tipo
# nascendo "fixo", bastava preencher o percentual e salvar: `FeeCreate` exigia
# apenas "valor OU percentual", então passava — e `routers/honorarios_oab.py`
# só lê o percentual quando `tipo in (exito, misto)`. O registro ficava sem
# valor fixo e com um percentual que nenhum cálculo enxerga: cobrança que
# existe no cadastro e não existe na conta. Mesma classe do honorário vazio.

@pytest.mark.parametrize("tipo", ["fixo", "por_hora", "custas_despesas", "sucumbencia"])
def test_percentual_recusado_em_tipo_que_nao_calcula(tipo: str):
    with pytest.raises(ValidationError) as e:
        FeeCreate(descricao="Honorario", client_id="c1", tipo=tipo,
                  percentual_exito=Decimal("20"))
    msg = str(e.value)
    assert "percentual_exito" in msg and tipo in msg


@pytest.mark.parametrize("tipo", ["exito", "misto"])
def test_percentual_aceito_nos_tipos_que_calculam(tipo: str):
    f = FeeCreate(descricao="Honorario", client_id="c1", tipo=tipo,
                  percentual_exito=Decimal("20"))
    assert f.percentual_exito == Decimal("20") and f.valor is None


def test_valor_fixo_continua_valido_em_qualquer_tipo():
    """A restrição é do percentual; nenhum tipo perde o caminho em reais."""
    for tipo in ("fixo", "por_hora", "custas_despesas", "sucumbencia", "exito"):
        f = FeeCreate(descricao="Honorario", client_id="c1", tipo=tipo,
                      valor=Decimal("5000"))
        assert f.valor == Decimal("5000")


def test_exito_com_piso_contratado_continua_valido():
    """Percentual E valor juntos — arranjo legítimo, não pode ter sido fechado."""
    f = FeeCreate(descricao="Exito com piso", client_id="c1", tipo="exito",
                  valor=Decimal("2000"), percentual_exito=Decimal("15"))
    assert f.valor and f.percentual_exito
