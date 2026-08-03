"""Índice de risco: incompletude não pode ser lida como segurança (P0-023).

Caso sem NENHUM documento somava 15 pontos, 15 caía na faixa "baixo" e o painel
o pintava de verde. O índice mede o risco que se consegue ENXERGAR; sem base
documental não há o que enxergar, e afirmar "risco baixo" é a interface se
declarar tranquila justamente onde tem menos evidência para isso.

Função pura — não exige banco.
"""

from __future__ import annotations

import pytest

from app.routers.indice_risco import NIVEL_INDETERMINADO, _nivel


@pytest.mark.parametrize("indice", [0, 5, 15, 20, 25])
def test_sem_base_documental_nunca_devolve_baixo(indice):
    """Regressão direta: 15 é o placar de um caso cujo ÚNICO fator é a ausência
    de documentos. Antes vinha "baixo"; agora vem o nível neutro."""
    assert _nivel(indice, base_avaliavel=False) == NIVEL_INDETERMINADO


@pytest.mark.parametrize("indice", [0, 5, 15, 20, 25])
def test_com_documentos_a_faixa_baixa_continua_baixa(indice):
    """A trava é sobre a AUSÊNCIA de base, não sobre a faixa: caso documentado
    e sem fator de risco continua sendo — corretamente — risco baixo."""
    assert _nivel(indice, base_avaliavel=True) == "baixo"


@pytest.mark.parametrize(
    "indice,esperado",
    [(26, "medio"), (50, "medio"), (51, "alto"), (75, "alto"), (76, "critico"), (100, "critico")],
)
def test_risco_conhecido_prevalece_mesmo_sem_documentos(indice, esperado):
    """Acima de "baixo" existe risco medido — um caso sem documentos e com prazo
    vencido é "medio" de verdade. Rebaixar isso para indeterminado jogaria fora
    sinal real: o que não pode existir é "não sei nada" + "logo está seguro"."""
    assert _nivel(indice, base_avaliavel=False) == esperado
    assert _nivel(indice, base_avaliavel=True) == esperado


def test_avaliavel_por_padrao_preserva_os_chamadores_existentes():
    """`_nivel(x)` sem o parâmetro mantém o comportamento histórico — a mudança
    só alcança quem informa que a base é inavaliável."""
    assert _nivel(10) == "baixo"
    assert _nivel(90) == "critico"


def test_nivel_indeterminado_nao_colide_com_as_faixas():
    """O valor novo precisa ser distinguível: se colidisse com uma faixa, a
    interface voltaria a colorir o desconhecido como se fosse conhecido."""
    assert NIVEL_INDETERMINADO not in {"baixo", "medio", "alto", "critico"}
