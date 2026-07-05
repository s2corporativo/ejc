"""LRU de embeddings de query (IA-04 Fase 5).

Valida a política de cache (hit/miss, evicção LRU) e que uma query única já
cacheada NÃO recomputa o embedding.
"""
import pytest

from app.services import embedding_service as es


@pytest.fixture(autouse=True)
def _limpa_cache():
    es._QUERY_CACHE.clear()
    yield
    es._QUERY_CACHE.clear()


def test_put_get_basico():
    es._cache_query_put("query", "prescrição", [0.1, 0.2])
    assert es._cache_query_get("query", "prescrição") == [0.1, 0.2]
    assert es._cache_query_get("query", "outra") is None


def test_eviccao_respeita_o_limite():
    limite = es._QUERY_CACHE_MAX
    for i in range(limite + 10):
        es._cache_query_put("query", f"t{i}", [float(i)])
    assert len(es._QUERY_CACHE) == limite
    # os 10 mais antigos foram removidos; os recentes permanecem
    assert es._cache_query_get("query", "t0") is None
    assert es._cache_query_get("query", f"t{limite + 9}") == [float(limite + 9)]


def test_get_atualiza_recencia_lru():
    es._cache_query_put("query", "antigo", [1.0])
    es._cache_query_put("query", "novo", [2.0])
    # acessar "antigo" o torna o mais recente
    es._cache_query_get("query", "antigo")
    chaves = list(es._QUERY_CACHE.keys())
    assert chaves[-1] == ("query", "antigo")


async def test_query_cacheada_nao_recomputa(monkeypatch):
    # disponivel=True e provider local; se o cache for usado, _embed_sync (que
    # aqui explode) nunca é chamado.
    monkeypatch.setattr(es, "disponivel", lambda: True)
    monkeypatch.setattr(es, "_provider", lambda: "local")

    def _boom(*a, **k):
        raise AssertionError("não deveria recomputar: cache hit esperado")

    monkeypatch.setattr(es, "_embed_sync", _boom)
    es._cache_query_put("query", "habeas corpus", [0.5] * 3)

    out = await es.gerar_embeddings(["habeas corpus"], modo="query")
    assert out == [[0.5] * 3]
