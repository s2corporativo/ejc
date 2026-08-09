"""Regressão: revogação citada na ementa não prova revogação do ato atual."""
from app.services.ingestors import lexml


def test_ementa_que_menciona_outra_norma_revogada_nao_revoga_o_item_atual():
    item = {
        "titulo": "Lei nº 14.133, de 1º de abril de 2021",
        "ementa": (
            "Licitações e contratos administrativos. Aplica-se ao regime atual e "
            "faz referência à Lei nº 8.666/1993, revogada pela Lei nº 14.133/2021."
        ),
    }

    assert lexml.situacao_juridica(item, "legislacao") is None


def test_titulo_que_declara_a_propria_revogacao_continua_bloqueando():
    item = {
        "titulo": (
            "Lei nº 8.666, de 21 de junho de 1993 — "
            "Revogada pela Lei nº 14.133, de 2021"
        ),
        "ementa": "Regulamenta licitações e contratos no regime histórico.",
    }

    assert lexml.situacao_juridica(item, "legislacao") == "revogada"


def test_jurisprudencia_nunca_herda_status_normativo_da_ementa():
    item = {
        "titulo": "Acórdão sobre regime intertemporal de licitações",
        "ementa": "Lei nº 8.666/1993, revogada pela Lei nº 14.133/2021.",
    }

    assert lexml.situacao_juridica(item, "jurisprudencia") is None
