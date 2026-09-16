from __future__ import annotations

import pytest

from app.services.datajud_service import DataJudDesabilitadoError
from app.services.jurimetria_tribunais import agregacao, coleta, servico
from app.services.jurimetria_tribunais import tpu_desfechos as tpu


def _mov(codigo: int) -> dict:
    return {"codigo": codigo, "dataHora": "2026-01-15T10:00:00Z"}


def _doc(numero: str, assuntos: list[tuple[int, str]]) -> dict:
    return {
        "numeroProcesso": numero,
        "grau": "G1",
        "orgaoJulgador": {
            "nome": "1ª Vara Cível da Comarca de Betim",
            "codigoMunicipioIBGE": 3106705,
        },
        "dataAjuizamento": "2025-01-01T00:00:00Z",
        "assuntos": [
            {"codigo": codigo, "nome": nome} for codigo, nome in assuntos
        ],
        "movimentos": [_mov(219)],
    }


def test_assuntos_multiplos_e_cruzamento_municipio_assunto():
    docs = [
        _doc(
            "0000001",
            [
                (9985, "Indenização por Dano Moral"),
                (10433, "Cobrança"),
            ],
        )
    ]
    resultado = agregacao.agregar(docs, ["betim"])

    assuntos = {a["assunto_codigo"] for a in resultado["por_assunto"]}
    assert assuntos == {"9985", "10433"}
    cruzamentos = {
        (a["municipio"], a["assunto_codigo"])
        for a in resultado["por_municipio_assunto"]
    }
    assert cruzamentos == {("betim", "9985"), ("betim", "10433")}
    # O total do universo continua contando o processo uma única vez.
    assert resultado["total"]["n"] == 1


def test_filtro_de_assunto_nao_reclassifica_para_o_primeiro_assunto():
    docs = [
        _doc(
            "0000001",
            [
                (9985, "Indenização por Dano Moral"),
                (10433, "Cobrança"),
            ],
        )
    ]
    resultado = agregacao.agregar(docs, ["betim"], assunto_filtro=10433)
    assert [a["assunto_codigo"] for a in resultado["por_assunto"]] == ["10433"]


def test_lote_truncado_suprime_taxas_e_tempos():
    agregado = agregacao.agregar([_doc("0000001", [(9985, "Dano Moral")])], ["betim"])
    protegido = servico._suprimir_taxas_se_truncado(
        agregado,
        {"truncado": True},
    )
    assert protegido["amostra_truncada"] is True
    assert protegido["total"]["taxa_procedencia"] is None
    assert protegido["total"]["taxa_acordo"] is None
    assert protegido["total"]["tempo_sentenca"]["mediana_dias"] is None


def test_reforma_geografica_nao_e_publicada_sem_join_do_processo_origem():
    agregado = agregacao.agregar([_doc("0000001", [(9985, "Dano Moral")])], ["betim"])
    servico._desabilitar_reforma_geografica(agregado)
    assert agregado["reforma_2grau"]["disponivel"] is False
    assert agregado["reforma_2grau"]["taxa_reforma"] is None
    assert "processo de origem" in agregado["reforma_2grau"]["motivo"]


@pytest.mark.asyncio
async def test_kill_switch_e_verificado_antes_de_servir_cache(monkeypatch):
    coleta.limpar_cache()
    query = {"query": {"match_all": {}}}
    chave = coleta._chave_cache(query, 10, coleta.ALIAS_TJMG)
    coleta._CACHE[chave] = (
        99999999999.0,
        [{"numeroProcesso": "1"}],
        {
            "cache": False,
            "coletado_em": "2026-09-13T20:00:00Z",
            "n_documentos": 1,
            "alias": coleta.ALIAS_TJMG,
        },
    )

    def bloqueado():
        raise DataJudDesabilitadoError("revogado")

    monkeypatch.setattr(coleta, "_headers", bloqueado)
    with pytest.raises(DataJudDesabilitadoError):
        await coleta._coletar_alias(
            coleta.ALIAS_TJMG,
            query,
            maximo=10,
            ttl=3600,
        )


@pytest.mark.asyncio
async def test_cache_preserva_timestamp_da_coleta(monkeypatch):
    coleta.limpar_cache()
    query = {"query": {"match_all": {}}}

    monkeypatch.setattr(
        coleta,
        "_headers",
        lambda: {"Authorization": "APIKey teste", "Content-Type": "application/json"},
    )

    async def fake_busca(*args, **kwargs):
        return [{"_source": {"numeroProcesso": "1"}}]

    monkeypatch.setattr(coleta, "buscar_lote_paginado", fake_busca)

    _, primeira = await coleta._coletar_alias(
        coleta.ALIAS_TJMG,
        query,
        maximo=10,
        ttl=3600,
    )
    _, segunda = await coleta._coletar_alias(
        coleta.ALIAS_TJMG,
        query,
        maximo=10,
        ttl=3600,
    )

    assert primeira["cache"] is False
    assert segunda["cache"] is True
    assert segunda["coletado_em"] == primeira["coletado_em"]
    coleta.limpar_cache()
