import inspect

import pytest

from app.routers.indice_risco import _nivel, recalcular


@pytest.mark.parametrize(
    ("indice", "esperado"),
    [(0, "baixo"), (25, "baixo"), (26, "medio"), (50, "medio"),
     (51, "alto"), (75, "alto"), (76, "critico"), (100, "critico")],
)
def test_niveis_permanecem_compativeis_com_triagem_completa(indice, esperado):
    assert _nivel(indice, triagem_completa=True) == esperado


@pytest.mark.parametrize("indice", [0, 15, 50, 100])
def test_triagem_sem_documentos_nunca_e_classificada_como_baixo(indice):
    assert _nivel(indice, triagem_completa=False) == "incompleto"


def test_recalculo_vincula_incompletude_ao_total_de_documentos():
    fonte = inspect.getsource(recalcular)
    assert 'fatores["triagem_incompleta"] = True' in fonte
    assert "triagem_completa=total_docs > 0" in fonte
    assert '"avaliacao_conclusiva": nivel != "incompleto"' in fonte
