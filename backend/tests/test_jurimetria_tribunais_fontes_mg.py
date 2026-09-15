from __future__ import annotations

import pytest

from app.services.jurimetria_tribunais import servico
from app.services.jurimetria_tribunais.coleta import (
    eh_jec,
    filtrar_jec,
    montar_query_trt3,
)


def test_query_trt3_sem_filtros_usa_match_all():
    assert montar_query_trt3() == {"query": {"match_all": {}}}


def test_query_trt3_preserva_filtros_tpu_e_periodo():
    query = montar_query_trt3(
        classe=1116,
        assunto=2583,
        desde="2025-01-01",
        ate="2026-01-01",
    )
    filtros = query["query"]["bool"]["filter"]
    assert {"term": {"classe.codigo": 1116}} in filtros
    assert {"term": {"assuntos.codigo": 2583}} in filtros
    assert {
        "range": {
            "dataAjuizamento": {"gte": "2025-01-01", "lte": "2026-01-01"}
        }
    } in filtros


@pytest.mark.parametrize(
    ("doc", "esperado"),
    [
        ({"grau": "JE", "orgaoJulgador": {"nome": "1ª Unidade"}}, True),
        (
            {
                "grau": "G1",
                "orgaoJulgador": {"nome": "Juizado Especial Cível de Betim"},
            },
            True,
        ),
        (
            {
                "grau": "G2",
                "orgaoJulgador": {"nome": "1ª Turma Recursal de Minas Gerais"},
            },
            True,
        ),
        (
            {"grau": "G1", "orgaoJulgador": {"nome": "1ª Vara Cível de Betim"}},
            False,
        ),
    ],
)
def test_classificacao_jec_apenas_por_metadados(doc, esperado):
    assert eh_jec(doc) is esperado


def test_filtrar_jec_nao_duplica_lote_tjmg():
    docs = [
        {
            "numeroProcesso": "1",
            "grau": "JE",
            "orgaoJulgador": {"nome": "Juizado Especial Cível"},
        },
        {
            "numeroProcesso": "2",
            "grau": "G1",
            "orgaoJulgador": {"nome": "2ª Vara Cível"},
        },
    ]
    recorte = filtrar_jec(docs)
    assert [d["numeroProcesso"] for d in recorte] == ["1"]
    assert len(docs) == 2


@pytest.mark.asyncio
async def test_servico_mantem_tjmg_e_anexa_jec_e_trt3(monkeypatch):
    tjmg_docs = [
        {
            "numeroProcesso": "00000010020268130024",
            "grau": "JE",
            "orgaoJulgador": {
                "nome": "Juizado Especial Cível da Comarca de Betim",
                "codigoMunicipioIBGE": 3106705,
            },
            "assuntos": [{"codigo": 9985, "nome": "Dano Moral"}],
            "movimentos": [],
        }
    ]
    trt3_docs = [
        {
            "numeroProcesso": "00000010020265030001",
            "grau": "G1",
            "orgaoJulgador": {"nome": "1ª Vara do Trabalho"},
            "assuntos": [{"codigo": 2583, "nome": "Horas Extras"}],
            "movimentos": [],
        }
    ]

    async def fake_tjmg(*args, **kwargs):
        return tjmg_docs, {
            "cache": False,
            "coletado_em": "2026-09-13T20:00:00Z",
            "maximo": 2000,
            "n_documentos": 1,
            "truncado": False,
            "alias": "api_publica_tjmg",
        }

    async def fake_trt3(*args, **kwargs):
        return trt3_docs, {
            "cache": False,
            "coletado_em": "2026-09-13T20:00:00Z",
            "maximo": 2000,
            "n_documentos": 1,
            "truncado": False,
            "alias": "api_publica_trt3",
        }

    monkeypatch.setattr(servico, "coletar", fake_tjmg)
    monkeypatch.setattr(servico, "coletar_trt3", fake_trt3)

    resposta = await servico.desfechos(["betim"])

    assert resposta["escopo"]["tribunal"] == "TJMG"
    assert resposta["fontes_complementares"]["jec_tjmg"]["disponivel"] is True
    assert (
        resposta["fontes_complementares"]["jec_tjmg"]["coleta"][
            "derivado_sem_nova_consulta"
        ]
        is True
    )
    assert resposta["fontes_complementares"]["trt3"]["disponivel"] is True
    assert resposta["fontes_complementares"]["trt3"]["escopo"]["tribunal"] == "TRT3"
