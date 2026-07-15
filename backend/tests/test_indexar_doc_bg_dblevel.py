"""Auditoria RAG — `_indexar_doc_bg` (app/routers/rag.py) tudo-ou-nada.

Bug real de produção: quando o provider de embeddings devolvia MENOS vetores
do que chunks pedidos, `zip(chunks, vetores)` truncava silenciosamente — os
chunks "sobrando" ficavam com `embedding=NULL` para sempre, mas o doc era
marcado `status_indexacao='indexado'` do mesmo jeito (26.107 chunks órfãos
encontrados em produção). Corrigido em duas camadas:
  1. `gerar_embeddings` agora rejeita (retorna None) contagem de vetores que
     não bate com a de textos pedidos (test_embedding_service.py).
  2. `_indexar_doc_bg` só aplica os vetores e marca 'indexado' se a contagem
     bater 1:1; senão, NENHUM chunk é tocado e o doc não vira 'indexado'.

Requer Postgres com pg_trgm + pgvector e migrations aplicadas (RUN_DB_TESTS=1)
— roda ORM real (select/update) via AsyncSessionLocal, como _indexar_doc_bg faz.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres+pgvector com migrations (defina RUN_DB_TESTS=1)",
)


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


async def _criar_doc_com_chunks(db, n_chunks: int) -> str:
    doc_id = str(uuid4())
    await db.execute(text(
        "INSERT INTO knowledge_docs (id, titulo, categoria, status_indexacao) "
        "VALUES (:id, 'DOC_TESTE_INDEXAR_BG', 'legislacao', 'pendente')"
    ), {"id": doc_id})
    for i in range(n_chunks):
        await db.execute(text(
            "INSERT INTO knowledge_chunks (id, doc_id, chunk_index, conteudo) "
            "VALUES (:id, :doc, :idx, :cont)"
        ), {"id": str(uuid4()), "doc": doc_id, "idx": i, "cont": f"conteudo chunk {i}"})
    return doc_id


async def test_contagem_divergente_nao_aplica_embedding_parcial(monkeypatch):
    """gerar_embeddings devolvendo MENOS vetores que chunks: nenhum chunk deve
    ser tocado e o doc NÃO pode virar 'indexado'."""
    from app.core.database import AsyncSessionLocal
    import app.routers.rag as rag_router

    monkeypatch.setattr(rag_router, "emb_disponivel", lambda: True)

    async def _vetores_curtos(textos):
        # gerar_embeddings de verdade já rejeitaria isso (contagem não bate),
        # mas testamos a defesa de _indexar_doc_bg mesmo se algo escapasse.
        return [[0.0] * 768]  # 1 vetor para N chunks

    monkeypatch.setattr(rag_router, "gerar_embeddings", _vetores_curtos)

    async with AsyncSessionLocal() as db:
        doc_id = await _criar_doc_com_chunks(db, 3)
        await db.commit()
        try:
            await rag_router._indexar_doc_bg(doc_id)

            row = (await db.execute(text(
                "SELECT status_indexacao FROM knowledge_docs WHERE id=:id"
            ), {"id": doc_id})).one()
            assert row.status_indexacao != "indexado", (
                "doc não pode virar 'indexado' com contagem de vetores divergente")

            chunks = (await db.execute(text(
                "SELECT embedding FROM knowledge_chunks WHERE doc_id=:id"
            ), {"id": doc_id})).all()
            assert all(c.embedding is None for c in chunks), (
                "nenhum chunk pode ficar com embedding parcial aplicado")
        finally:
            await db.execute(text("DELETE FROM knowledge_docs WHERE id=:id"), {"id": doc_id})
            await db.commit()


async def test_contagem_certa_aplica_e_marca_indexado(monkeypatch):
    """gerar_embeddings devolvendo a contagem certa: todos os chunks recebem
    embedding e o doc vira 'indexado'."""
    from app.core.database import AsyncSessionLocal
    import app.routers.rag as rag_router

    monkeypatch.setattr(rag_router, "emb_disponivel", lambda: True)

    async def _vetores_certos(textos):
        return [[0.0] * 768 for _ in textos]

    monkeypatch.setattr(rag_router, "gerar_embeddings", _vetores_certos)

    async with AsyncSessionLocal() as db:
        doc_id = await _criar_doc_com_chunks(db, 3)
        await db.commit()
        try:
            await rag_router._indexar_doc_bg(doc_id)

            row = (await db.execute(text(
                "SELECT status_indexacao FROM knowledge_docs WHERE id=:id"
            ), {"id": doc_id})).one()
            assert row.status_indexacao == "indexado"

            chunks = (await db.execute(text(
                "SELECT embedding FROM knowledge_chunks WHERE doc_id=:id"
            ), {"id": doc_id})).all()
            assert all(c.embedding is not None for c in chunks)
        finally:
            await db.execute(text("DELETE FROM knowledge_docs WHERE id=:id"), {"id": doc_id})
            await db.commit()
