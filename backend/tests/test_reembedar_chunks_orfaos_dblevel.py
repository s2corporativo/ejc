"""Auditoria RAG — validação ROW-LEVEL (Postgres real) da correção dos 26.107
chunks órfãos: scripts/reconciliar_status_rag.py (query corrigida) e
scripts/reembedar_chunks_orfaos.py (remediação dos dados já contaminados).

Requer Postgres com pg_trgm + pgvector e migrations aplicadas (RUN_DB_TESTS=1).
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.services.embedding_service import EMBED_DIM  # dim configurável (O-2): casa com a coluna

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres+pgvector com migrations (defina RUN_DB_TESTS=1)",
)


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


async def _criar_doc(db, *, status="pendente", n_chunks_com_embedding=0, n_chunks_sem=0):
    doc_id = str(uuid4())
    await db.execute(text(
        "INSERT INTO knowledge_docs (id, titulo, categoria, status_indexacao) "
        "VALUES (:id, 'DOC_TESTE_RECONCILIA', 'legislacao', :s)"
    ), {"id": doc_id, "s": status})
    vec = "[" + ",".join(["0.000000"] * EMBED_DIM) + "]"
    idx = 0
    for _ in range(n_chunks_com_embedding):
        await db.execute(text(
            "INSERT INTO knowledge_chunks (id, doc_id, chunk_index, conteudo, embedding) "
            "VALUES (:id, :doc, :idx, 'c', CAST(:v AS vector))"
        ), {"id": str(uuid4()), "doc": doc_id, "idx": idx, "v": vec})
        idx += 1
    for _ in range(n_chunks_sem):
        await db.execute(text(
            "INSERT INTO knowledge_chunks (id, doc_id, chunk_index, conteudo) "
            "VALUES (:id, :doc, :idx, 'c')"
        ), {"id": str(uuid4()), "doc": doc_id, "idx": idx})
        idx += 1
    return doc_id


async def test_reconciliador_so_marca_indexado_quando_todos_os_chunks_tem_embedding():
    """Doc com 1 chunk embedado e 1 órfão NÃO deve virar 'indexado' (bug antigo:
    EXISTS pegava qualquer chunk e marcava o doc inteiro)."""
    from app.core.database import AsyncSessionLocal
    from scripts.reconciliar_status_rag import reconciliar

    async with AsyncSessionLocal() as db:
        doc_parcial = await _criar_doc(db, n_chunks_com_embedding=1, n_chunks_sem=1)
        doc_completo = await _criar_doc(db, n_chunks_com_embedding=2, n_chunks_sem=0)
        doc_vazio = await _criar_doc(db, n_chunks_com_embedding=0, n_chunks_sem=2)
        await db.commit()
        try:
            await reconciliar()

            rows = {r.id: r.status_indexacao for r in (await db.execute(text(
                "SELECT id, status_indexacao FROM knowledge_docs WHERE id = ANY(:ids)"
            ), {"ids": [doc_parcial, doc_completo, doc_vazio]})).all()}

            assert rows[doc_parcial] != "indexado", (
                "doc parcialmente embedado não pode virar 'indexado' (bug EXISTS-any)")
            assert rows[doc_completo] == "indexado", (
                "doc com TODOS os chunks embedados deve virar 'indexado'")
            assert rows[doc_vazio] != "indexado"
        finally:
            for d in (doc_parcial, doc_completo, doc_vazio):
                await db.execute(text("DELETE FROM knowledge_docs WHERE id=:id"), {"id": d})
            await db.commit()


async def test_reembedar_conserta_doc_ja_marcado_indexado_com_chunk_orfao(monkeypatch):
    """O caso real de produção: doc JÁ está 'indexado' (rótulo incorreto de
    execução anterior do reconciliador antigo) mas tem chunk com embedding NULL.
    O script de remediação deve reembedar o órfão e manter o status correto."""
    from app.core.database import AsyncSessionLocal
    import scripts.reembedar_chunks_orfaos as reemb

    async def _vetores_ok(textos):
        return [[0.0] * EMBED_DIM for _ in textos]

    monkeypatch.setattr(reemb, "gerar_embeddings", _vetores_ok)
    monkeypatch.setattr(reemb, "emb_disponivel", lambda: True)

    async with AsyncSessionLocal() as db:
        # simula o dado contaminado: status='indexado' mas 1 chunk sem embedding
        doc_id = await _criar_doc(db, status="indexado",
                                  n_chunks_com_embedding=1, n_chunks_sem=1)
        await db.commit()
        try:
            await reemb.reembedar(batch_size=10)

            row = (await db.execute(text(
                "SELECT status_indexacao FROM knowledge_docs WHERE id=:id"
            ), {"id": doc_id})).one()
            assert row.status_indexacao == "indexado"

            chunks = (await db.execute(text(
                "SELECT embedding FROM knowledge_chunks WHERE doc_id=:id"
            ), {"id": doc_id})).all()
            assert all(c.embedding is not None for c in chunks), (
                "todos os chunks (inclusive o antes órfão) devem ter embedding")
        finally:
            await db.execute(text("DELETE FROM knowledge_docs WHERE id=:id"), {"id": doc_id})
            await db.commit()


async def test_reembedar_dry_run_nao_grava_nada(monkeypatch):
    from app.core.database import AsyncSessionLocal
    import scripts.reembedar_chunks_orfaos as reemb

    monkeypatch.setattr(reemb, "emb_disponivel", lambda: True)

    async with AsyncSessionLocal() as db:
        doc_id = await _criar_doc(db, status="indexado",
                                  n_chunks_com_embedding=1, n_chunks_sem=1)
        await db.commit()
        try:
            await reemb.reembedar(batch_size=10, dry_run=True)

            chunks = (await db.execute(text(
                "SELECT embedding FROM knowledge_chunks WHERE doc_id=:id"
            ), {"id": doc_id})).all()
            assert sum(1 for c in chunks if c.embedding is None) == 1, (
                "dry-run não pode gravar embedding em nada")
        finally:
            await db.execute(text("DELETE FROM knowledge_docs WHERE id=:id"), {"id": doc_id})
            await db.commit()
