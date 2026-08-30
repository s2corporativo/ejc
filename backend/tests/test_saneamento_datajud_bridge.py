"""Extensões ao datajud_service para o módulo de saneamento:
buscar_documento_saneamento, buscar_lote_paginado e o limitador de
requisições (_aguardar_rate_limit — DATAJUD_RATE_LIMIT_RPS, "A VERIFICAR":
nenhuma fonte oficial do CNJ declara rate limit da API Pública).

Sem chamada de rede: `_datajud_search` é sempre substituído por um duplo de
teste, seguindo o mesmo padrão de test_andamentos_datajud.py.
"""
from __future__ import annotations

import time

import pytest

from app.core.config import get_settings
from app.services import datajud_service


@pytest.fixture(autouse=True)
def _limpar_estado_rate_limit():
    """Isola o estado global do limitador entre testes."""
    datajud_service._ULTIMA_CONCESSAO = 0.0
    yield
    datajud_service._ULTIMA_CONCESSAO = 0.0


def _ligar_datajud(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "DATAJUD_ENABLED", True)
    monkeypatch.setattr(s, "DATAJUD_API_KEY", "chave-publica-cnj-teste")
    return s


# Mesmo número oficial usado nos demais arquivos do módulo.
NUM_CNJ_OFICIAL = "00008323520184013202"  # TRF1 (segmento 4, tribunal 01)


# ── buscar_documento_saneamento ──────────────────────────────────────────────

async def test_buscar_documento_saneamento_desligado_levanta(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "DATAJUD_ENABLED", False)
    with pytest.raises(datajud_service.DataJudDesabilitadoError):
        await datajud_service.buscar_documento_saneamento(NUM_CNJ_OFICIAL)


async def test_buscar_documento_saneamento_sem_chave_levanta(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "DATAJUD_ENABLED", True)
    monkeypatch.setattr(s, "DATAJUD_API_KEY", "")
    with pytest.raises(datajud_service.DataJudDesabilitadoError):
        await datajud_service.buscar_documento_saneamento(NUM_CNJ_OFICIAL)


async def test_buscar_documento_saneamento_tribunal_nao_mapeado_levanta(monkeypatch):
    _ligar_datajud(monkeypatch)
    # Segmento 6 (Justiça Eleitoral) — não mapeado (pendência explícita).
    numero_nao_mapeado = "00008320020186133202"
    with pytest.raises(datajud_service.TribunalNaoMapeadoError):
        await datajud_service.buscar_documento_saneamento(numero_nao_mapeado)


async def test_buscar_documento_saneamento_devolve_source_cru(monkeypatch):
    _ligar_datajud(monkeypatch)

    fonte = {
        "numeroProcesso": NUM_CNJ_OFICIAL, "classe": {"codigo": 9},
        "orgaoJulgador": {"codigo": 1}, "dataAjuizamento": "2018-01-10T00:00:00Z",
        "tribunal": "TRF1", "grau": "G1", "formato": {"codigo": 1},
        "sistema": {"codigo": 1}, "nivelSigilo": 0,
        "movimentos": [{"codigo": 246, "nome": "Arquivado", "dataHora": "2020-01-01T00:00:00Z"}],
    }

    async def _fake_search(alias, payload, headers):
        assert alias == "api_publica_trf1"
        return {"hits": {"hits": [{"_source": fonte}]}}

    monkeypatch.setattr(datajud_service, "_datajud_search", _fake_search)
    doc = await datajud_service.buscar_documento_saneamento(NUM_CNJ_OFICIAL)
    assert doc == fonte
    assert doc["nivelSigilo"] == 0  # campo que consultar_processo() descarta


async def test_buscar_documento_saneamento_sem_hits_e_none(monkeypatch):
    _ligar_datajud(monkeypatch)

    async def _fake_search(alias, payload, headers):
        return {"hits": {"hits": []}}

    monkeypatch.setattr(datajud_service, "_datajud_search", _fake_search)
    assert await datajud_service.buscar_documento_saneamento(NUM_CNJ_OFICIAL) is None


# ── buscar_lote_paginado ──────────────────────────────────────────────────────

async def test_buscar_lote_paginado_encadeia_search_after():
    chamadas = []

    async def _fake_search(alias, payload, headers):
        chamadas.append(payload)
        pagina = len(chamadas)
        if pagina == 1:
            return {"hits": {"hits": [
                {"_source": {"n": 1}, "sort": [1]},
                {"_source": {"n": 2}, "sort": [2]},
            ]}}
        if pagina == 2:
            return {"hits": {"hits": [{"_source": {"n": 3}, "sort": [3]}]}}
        raise AssertionError("não deveria pedir uma terceira página")

    import app.services.datajud_service as ds
    orig = ds._datajud_search
    ds._datajud_search = _fake_search  # type: ignore[assignment]
    try:
        hits = await ds.buscar_lote_paginado(
            "api_publica_trf1", {"query": {"match_all": {}}}, {}, tamanho_pagina=2,
        )
    finally:
        ds._datajud_search = orig  # type: ignore[assignment]

    assert [h["_source"]["n"] for h in hits] == [1, 2, 3]
    # 2ª chamada usa o `sort` do último hit da 1ª página como search_after.
    assert chamadas[1]["search_after"] == [2]


async def test_buscar_lote_paginado_respeita_o_maximo():
    async def _fake_search(alias, payload, headers):
        return {"hits": {"hits": [
            {"_source": {"n": i}, "sort": [i]} for i in range(payload["size"])
        ]}}

    import app.services.datajud_service as ds
    orig = ds._datajud_search
    ds._datajud_search = _fake_search  # type: ignore[assignment]
    try:
        hits = await ds.buscar_lote_paginado(
            "api_publica_trf1", {"query": {"match_all": {}}}, {},
            tamanho_pagina=10, maximo=15,
        )
    finally:
        ds._datajud_search = orig  # type: ignore[assignment]

    assert len(hits) == 15


async def test_buscar_lote_paginado_para_quando_pagina_vem_vazia():
    async def _fake_search(alias, payload, headers):
        return {"hits": {"hits": []}}

    import app.services.datajud_service as ds
    orig = ds._datajud_search
    ds._datajud_search = _fake_search  # type: ignore[assignment]
    try:
        hits = await ds.buscar_lote_paginado(
            "api_publica_trf1", {"query": {"match_all": {}}}, {},
        )
    finally:
        ds._datajud_search = orig  # type: ignore[assignment]
    assert hits == []


# ── limitador de requisições ──────────────────────────────────────────────────

async def test_rate_limit_espaca_chamadas_consecutivas(monkeypatch):
    s = get_settings()
    # RPS alto o bastante para não deixar o teste lento, baixo o bastante
    # para o intervalo mínimo ser mensurável.
    monkeypatch.setattr(s, "DATAJUD_RATE_LIMIT_RPS", 20.0)  # intervalo = 50ms
    inicio = time.monotonic()
    await datajud_service._aguardar_rate_limit()
    await datajud_service._aguardar_rate_limit()
    decorrido = time.monotonic() - inicio
    assert decorrido >= 0.05 * 0.9  # tolerância para jitter do scheduler


async def test_rate_limit_zero_desliga_o_limitador(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "DATAJUD_RATE_LIMIT_RPS", 0.0)
    inicio = time.monotonic()
    for _ in range(5):
        await datajud_service._aguardar_rate_limit()
    assert time.monotonic() - inicio < 0.05
