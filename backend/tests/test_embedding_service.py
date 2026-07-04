"""Busca semântica RAG — provider local de embeddings (fastembed, mockado).

Garante, SEM baixar modelo no CI:
- dimensão do vetor casa com a coluna pgvector vector(768);
- caminho local gera vetores via singleton mockado (asyncio.to_thread);
- fallback gracioso: erro ou dimensão errada → None (busca cai p/ textual);
- EMBEDDINGS_ENABLED=false mantém tudo desligado (default de código).
"""
import numpy as np
import pytest

from app.services import embedding_service as es


class _FakeModel:
    """Substitui fastembed.TextEmbedding: registra entradas, devolve vetores."""

    def __init__(self, dim: int = es.EMBED_DIM, explode: bool = False):
        self.dim = dim
        self.explode = explode
        self.entradas: list[str] = []

    def embed(self, textos):
        if self.explode:
            raise RuntimeError("onnx quebrou")
        self.entradas.extend(textos)
        for _ in textos:
            yield np.zeros(self.dim, dtype=np.float32)


@pytest.fixture
def _local_on(monkeypatch):
    """Liga embeddings locais e limpa caches do módulo (singleton/flag)."""
    monkeypatch.setattr(es.settings, "EMBEDDINGS_ENABLED", True)
    monkeypatch.setattr(es.settings, "EMBEDDINGS_PROVIDER", "local")
    monkeypatch.setattr(es, "_DISPONIVEL", None)
    monkeypatch.setattr(es, "_model", None)
    yield monkeypatch


def test_dimensao_do_modelo_casa_com_pgvector():
    # Migration 013: knowledge_chunks.embedding é vector(768).
    assert es.EMBED_DIM == 768


def test_modelo_mpnet_nao_usa_prefixo_e5():
    assert "e5" not in es.MODEL_NAME.lower()
    assert es._prefixo("query") == ""
    assert es._prefixo("passage") == ""


async def test_disabled_por_default_nao_gera(monkeypatch):
    monkeypatch.setattr(es.settings, "EMBEDDINGS_ENABLED", False)
    assert es.disponivel() is False
    assert await es.gerar_embeddings(["qualquer texto"]) is None


async def test_local_gera_vetor_dimensao_certa(_local_on):
    fake = _FakeModel()
    _local_on.setattr(es, "_get_model", lambda: fake)

    vetores = await es.gerar_embeddings(["dano moral", "rescisão indireta"], modo="query")

    assert vetores is not None and len(vetores) == 2
    assert all(len(v) == es.EMBED_DIM for v in vetores)
    assert all(isinstance(v, list) for v in vetores)
    # mpnet: texto vai cru, sem prefixo E5
    assert fake.entradas == ["dano moral", "rescisão indireta"]


async def test_erro_no_modelo_retorna_none_sem_excecao(_local_on, caplog):
    _local_on.setattr(es, "_get_model", lambda: _FakeModel(explode=True))
    with caplog.at_level("WARNING", logger="ejc.embeddings"):
        assert await es.gerar_embeddings(["texto"]) is None
    assert any("Falha ao gerar embeddings" in r.message for r in caplog.records)


async def test_dimensao_divergente_descartada(_local_on, caplog):
    _local_on.setattr(es, "_get_model", lambda: _FakeModel(dim=384))
    with caplog.at_level("WARNING", logger="ejc.embeddings"):
        assert await es.gerar_embeddings(["texto"]) is None


async def test_lista_vazia_retorna_none(_local_on):
    assert await es.gerar_embeddings([]) is None


def test_singleton_lazy_nao_carrega_no_import():
    # O import do módulo nunca deve materializar o modelo (boot leve).
    assert es._model is None or isinstance(es._model, _FakeModel) is False


async def test_rag_cai_para_textual_quando_embedding_falha(monkeypatch):
    """buscar_contexto_rag: embeddings ligados mas gerar_embeddings → None
    deve executar a busca textual (ILIKE), sem exceção ao chamador."""
    from app.services import ai_service

    monkeypatch.setattr(es, "disponivel", lambda: True)

    async def _sem_vetores(textos, modo="passage"):
        return None

    monkeypatch.setattr(es, "gerar_embeddings", _sem_vetores)

    class _CaptureDB:
        def __init__(self):
            self.sqls: list[str] = []

        async def execute(self, sql, params=None):
            self.sqls.append(str(sql))
            return []

    db = _CaptureDB()
    out = await ai_service.buscar_contexto_rag(db, "dano moral consumidor")
    assert out == []
    assert len(db.sqls) == 1
    assert "ILIKE" in db.sqls[0]          # caiu no textual
    assert "<=>" not in db.sqls[0]        # não tentou SQL vetorial sem vetor
