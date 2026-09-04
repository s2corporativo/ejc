"""Busca semântica RAG — provider local de embeddings (fastembed, mockado).

Garante, SEM baixar modelo no CI:
- dimensão do vetor casa com a coluna pgvector vector(1024);
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
        # Registra o batch_size de cada chamada — é o contrato que contém a
        # memória do ONNX (incidente de 2026-08-27, ver teste de regressão).
        self.lotes: list[int | None] = []

    def embed(self, textos, batch_size=None, **kwargs):
        if self.explode:
            raise RuntimeError("onnx quebrou")
        self.lotes.append(batch_size)
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
    # Migration 096 (O-2): knowledge_chunks.embedding é vector(1024) (BGE-M3).
    assert es.EMBED_DIM == 1024


def test_modelo_default_usa_protocolo_e5():
    assert "e5" in es.MODEL_NAME.lower()
    assert es._prefixo("query") == "query: "
    assert es._prefixo("passage") == "passage: "


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
    assert fake.entradas == ["query: dano moral", "query: rescisão indireta"]


async def test_encode_sempre_passa_batch_size_explicito(_local_on):
    """Regressão do incidente de 2026-08-27 (OOM global da VPS).

    `_embed_sync` entregava ao fastembed um lote do tamanho do documento e
    deixava o `batch_size` no default da biblioteca (256). Com documentos de
    centenas de chunks, o arena allocator do ONNX crescia até o maior lote já
    visto e não devolvia a memória: a reindexação chegou a 10 GB de anon-rss e
    o OOM-killer GLOBAL reiniciou containers de OUTROS sistemas na mesma VPS.

    O contrato defendido aqui é o teto explícito, não o número — por isso o
    assert é contra `es.EMBED_BATCH` (configurável) e contra um limite superior
    sanitário, e não contra o valor 16.
    """
    fake = _FakeModel()
    _local_on.setattr(es, "_get_model", lambda: fake)

    # Mais textos que o lote: o teto tem de valer justamente aqui.
    textos = [f"trecho {i}" for i in range(es.EMBED_BATCH * 3)]
    vetores = await es.gerar_embeddings(textos, modo="passage")

    assert vetores is not None and len(vetores) == len(textos)
    assert fake.lotes and all(lote == es.EMBED_BATCH for lote in fake.lotes), (
        "encode chamado sem batch_size explícito — o default do fastembed "
        "reabre o caminho do OOM de 2026-08-27"
    )
    assert 1 <= es.EMBED_BATCH <= 64, (
        "EMBED_BATCH alto demais para conter o arena allocator do ONNX numa "
        "VPS compartilhada com outros sistemas"
    )


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


async def test_contagem_divergente_do_provider_http_e_descartada(monkeypatch, caplog):
    """Auditoria RAG: um provider HTTP que devolve MENOS vetores do que textos
    pedidos não pode ser aceito — senão o chamador casaria vetor com chunk por
    posição (zip/index) e deixaria os chunks finais sem embedding, mesmo o doc
    sendo marcado 'indexado' (causa real de 26k chunks órfãos em produção)."""
    monkeypatch.setattr(es.settings, "EMBEDDINGS_ENABLED", True)
    monkeypatch.setattr(es.settings, "EMBEDDINGS_PROVIDER", "http")
    monkeypatch.setattr(es.settings, "EMBEDDINGS_API_URL", "http://fake/embed")

    async def _http_curto(textos, modo):
        # devolve só 2 vetores para 3 textos pedidos — dimensão certa, contagem errada
        return [[0.0] * es.EMBED_DIM, [0.0] * es.EMBED_DIM]

    monkeypatch.setattr(es, "_embed_http", _http_curto)

    with caplog.at_level("WARNING", logger="ejc.embeddings"):
        vetores = await es.gerar_embeddings(["um", "dois", "tres"], modo="passage")

    assert vetores is None
    assert any("contagem não bate" in r.message for r in caplog.records)


async def test_contagem_certa_do_provider_http_e_aceita(monkeypatch):
    monkeypatch.setattr(es.settings, "EMBEDDINGS_ENABLED", True)
    monkeypatch.setattr(es.settings, "EMBEDDINGS_PROVIDER", "http")
    monkeypatch.setattr(es.settings, "EMBEDDINGS_API_URL", "http://fake/embed")

    async def _http_certo(textos, modo):
        return [[0.0] * es.EMBED_DIM for _ in textos]

    monkeypatch.setattr(es, "_embed_http", _http_certo)

    vetores = await es.gerar_embeddings(["um", "dois", "tres"], modo="passage")
    assert vetores is not None and len(vetores) == 3


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
