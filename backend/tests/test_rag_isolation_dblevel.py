"""Isolamento do RAG por cliente — validação ROW-LEVEL contra Postgres real.

Este é o teste que fecha o Bloco 5: prova, com dados reais no banco, que a
busca RAG só recupera conteúdo RESTRITO (precedente_interno) do PRÓPRIO cliente
do escopo, nunca de outro. Complementa test_rag_isolation.py (que valida filtro
+ plumbing sem banco).

Requer Postgres com pg_trgm + pgvector e as migrations aplicadas. Roda só quando
RUN_DB_TESTS=1 (setado no job de CI `db-validation`); caso contrário, pula — não
tenta conectar em ambiente sem banco (nem em produção).

Determinístico: usa o caminho TEXTUAL (ILIKE) do buscar_contexto_rag — com
embeddings desligados (padrão) — então dois docs com o mesmo termo mas client_id
diferentes são diferenciados APENAS pelo filtro de escopo. Sem tuning de
similaridade semântica.
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

_TERMO = "usucapiaoextraordinariavintenaria"  # termo distintivo, casa ILIKE nos dois


async def _inserir_precedente(db, doc_id, client_id, titulo):
    await db.execute(
        text(
            "INSERT INTO knowledge_docs (id, titulo, categoria, client_id, status_indexacao) "
            "VALUES (:id, :tit, 'precedente_interno', :cli, 'indexado')"
        ),
        {"id": doc_id, "tit": titulo, "cli": client_id},
    )
    await db.execute(
        text(
            "INSERT INTO knowledge_chunks (id, doc_id, chunk_index, conteudo) "
            "VALUES (:id, :doc, 0, :cont)"
        ),
        {"id": str(uuid4()), "doc": doc_id, "cont": f"{_TERMO} caso {titulo} conteudo distintivo"},
    )


async def test_precedente_interno_isolado_por_cliente_rowlevel():
    from app.core.database import AsyncSessionLocal
    from app.services.ai_service import buscar_contexto_rag

    cli_A, cli_B = str(uuid4()), str(uuid4())
    doc_A, doc_B = str(uuid4()), str(uuid4())

    async with AsyncSessionLocal() as db:
        await _inserir_precedente(db, doc_A, cli_A, "PRECEDENTE_CLIENTE_A")
        await _inserir_precedente(db, doc_B, cli_B, "PRECEDENTE_CLIENTE_B")
        await db.commit()
        try:
            def titulos(res):
                return {r["titulo"] for r in res}

            # Escopo A → só vê o precedente de A.
            resA = await buscar_contexto_rag(
                db, _TERMO, limite=5, categorias=["precedente_interno"],
                modo_or=True, scope_client_id=cli_A,
            )
            tA = titulos(resA)
            assert "PRECEDENTE_CLIENTE_A" in tA, "precedente do próprio cliente deveria aparecer"
            assert "PRECEDENTE_CLIENTE_B" not in tA, "VAZAMENTO: precedente de outro cliente apareceu"

            # Escopo B → só vê o precedente de B.
            resB = await buscar_contexto_rag(
                db, _TERMO, limite=5, categorias=["precedente_interno"],
                modo_or=True, scope_client_id=cli_B,
            )
            tB = titulos(resB)
            assert "PRECEDENTE_CLIENTE_B" in tB
            assert "PRECEDENTE_CLIENTE_A" not in tB, "VAZAMENTO: precedente de outro cliente apareceu"

            # Sem escopo (None) → fail-closed: nenhum precedente restrito.
            resN = await buscar_contexto_rag(
                db, _TERMO, limite=5, categorias=["precedente_interno"],
                modo_or=True, scope_client_id=None,
            )
            tN = titulos(resN)
            assert "PRECEDENTE_CLIENTE_A" not in tN and "PRECEDENTE_CLIENTE_B" not in tN, (
                "fail-closed quebrado: conteúdo restrito recuperado sem escopo de cliente"
            )
        finally:
            await db.execute(
                text("DELETE FROM knowledge_chunks WHERE doc_id IN (:a, :b)"),
                {"a": doc_A, "b": doc_B},
            )
            await db.execute(
                text("DELETE FROM knowledge_docs WHERE id IN (:a, :b)"),
                {"a": doc_A, "b": doc_B},
            )
            await db.commit()


async def test_conteudo_publico_sempre_visivel_rowlevel():
    """Contraprova: conteúdo PÚBLICO (não restrito) aparece independentemente do
    escopo — o isolamento não pode ter quebrado a busca de legislação/súmulas."""
    from app.core.database import AsyncSessionLocal
    from app.services.ai_service import buscar_contexto_rag

    doc_pub = str(uuid4())
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO knowledge_docs (id, titulo, categoria, status_indexacao) "
                "VALUES (:id, 'SUMULA_PUBLICA_TESTE', 'sumula_stj', 'indexado')"
            ),
            {"id": doc_pub},
        )
        await db.execute(
            text(
                "INSERT INTO knowledge_chunks (id, doc_id, chunk_index, conteudo) "
                "VALUES (:id, :doc, 0, :cont)"
            ),
            {"id": str(uuid4()), "doc": doc_pub, "cont": f"{_TERMO} sumula publica de teste"},
        )
        await db.commit()
        try:
            # Mesmo sem escopo de cliente, público aparece.
            res = await buscar_contexto_rag(db, _TERMO, limite=5, modo_or=True, scope_client_id=None)
            assert "SUMULA_PUBLICA_TESTE" in {r["titulo"] for r in res}
        finally:
            await db.execute(text("DELETE FROM knowledge_chunks WHERE doc_id = :d"), {"d": doc_pub})
            await db.execute(text("DELETE FROM knowledge_docs WHERE id = :d"), {"d": doc_pub})
            await db.commit()
