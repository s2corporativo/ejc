"""Isolamento de escrita do RAG por cliente (Postgres/migration 109)."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import select, text


dblevel = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


@dblevel
async def test_mesma_chave_origem_pode_existir_em_clientes_diferentes():
    from app.core.database import AsyncSessionLocal
    from app.models.rag import KnowledgeDoc
    from app.services.ingestion_service import upsert_documento

    cli_a = str(uuid4())
    cli_b = str(uuid4())
    chave = f"externo:mesma-chave:{uuid4().hex[:8]}"

    async with AsyncSessionLocal() as db:
        await db.execute(
            text("INSERT INTO clients (id, tipo, nome, status) VALUES "
                 "(:a, 'PF', 'Cliente RAG A', 'ativo'), "
                 "(:b, 'PF', 'Cliente RAG B', 'ativo')"),
            {"a": cli_a, "b": cli_b},
        )
        try:
            r1 = await upsert_documento(
                db,
                titulo="Precedente restrito A",
                categoria="precedente_interno",
                conteudo="Conteúdo jurídico restrito do cliente A. " * 3,
                chave_origem=chave,
                client_id=cli_a,
                extra={"rag_status": "aprovado"},
                embutir_vetores=False,
            )
            r2 = await upsert_documento(
                db,
                titulo="Precedente restrito B",
                categoria="precedente_interno",
                conteudo="Conteúdo jurídico restrito do cliente B. " * 3,
                chave_origem=chave,
                client_id=cli_b,
                extra={"rag_status": "aprovado"},
                embutir_vetores=False,
            )
            await db.commit()

            docs = (await db.execute(
                select(KnowledgeDoc).where(
                    KnowledgeDoc.chave_origem == chave,
                    KnowledgeDoc.vigente.is_(True),
                ).order_by(KnowledgeDoc.client_id)
            )).scalars().all()
            assert r1 == "novo" and r2 == "novo"
            assert len(docs) == 2
            assert {d.client_id for d in docs} == {cli_a, cli_b}
            assert docs[0].hash_conteudo != docs[1].hash_conteudo
        finally:
            await db.rollback()
            await db.execute(
                text("DELETE FROM knowledge_docs WHERE chave_origem = :chave"),
                {"chave": chave},
            )
            await db.execute(
                text("DELETE FROM clients WHERE id IN (:a, :b)"),
                {"a": cli_a, "b": cli_b},
            )
            await db.commit()


@dblevel
async def test_mesmo_cliente_versiona_sem_afetar_outro_cliente():
    from app.core.database import AsyncSessionLocal
    from app.models.rag import KnowledgeDoc
    from app.services.ingestion_service import upsert_documento

    cli_a = str(uuid4())
    cli_b = str(uuid4())
    chave = f"externo:versionamento:{uuid4().hex[:8]}"

    async with AsyncSessionLocal() as db:
        await db.execute(
            text("INSERT INTO clients (id, tipo, nome, status) VALUES "
                 "(:a, 'PF', 'Cliente Version A', 'ativo'), "
                 "(:b, 'PF', 'Cliente Version B', 'ativo')"),
            {"a": cli_a, "b": cli_b},
        )
        try:
            for client_id, sufixo in ((cli_a, "A-v1"), (cli_b, "B-v1")):
                await upsert_documento(
                    db, titulo=sufixo, categoria="precedente_interno",
                    conteudo=(f"Conteúdo {sufixo} suficientemente longo. " * 3),
                    chave_origem=chave, client_id=client_id,
                    extra={"rag_status": "aprovado"}, embutir_vetores=False,
                )
            await db.commit()

            resultado = await upsert_documento(
                db, titulo="A-v2", categoria="precedente_interno",
                conteudo=("Conteúdo A versão dois atualizado. " * 3),
                chave_origem=chave, client_id=cli_a,
                extra={"rag_status": "aprovado"}, embutir_vetores=False,
            )
            await db.commit()

            vigentes = (await db.execute(
                select(KnowledgeDoc).where(
                    KnowledgeDoc.chave_origem == chave,
                    KnowledgeDoc.vigente.is_(True),
                )
            )).scalars().all()
            a = next(d for d in vigentes if d.client_id == cli_a)
            b = next(d for d in vigentes if d.client_id == cli_b)
            assert resultado == "atualizado"
            assert a.versao == 2
            assert b.versao == 1
        finally:
            await db.rollback()
            await db.execute(text("DELETE FROM knowledge_docs WHERE chave_origem = :c"), {"c": chave})
            await db.execute(text("DELETE FROM clients WHERE id IN (:a, :b)"), {"a": cli_a, "b": cli_b})
            await db.commit()
