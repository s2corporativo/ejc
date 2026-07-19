#!/usr/bin/env python
# ── scripts/reconciliar_status_rag.py ────────────────────────────────────────
# BUG-04 (fix REAL): reconcilia o flag `status_indexacao` dos documentos RAG.
#
# Diagnóstico de produção: os chunks (knowledge_chunks.embedding) JÁ estão todos
# vetorizados; o que ficou defasado foi o campo `knowledge_docs.status_indexacao`,
# que permaneceu 'pendente' em ~4.886 docs mesmo com os embeddings presentes.
# A vetorização (embeddings) NÃO é refeita — isto apenas corrige o rótulo.
#
# CORREÇÃO (auditoria RAG): a versão original desta query usava EXISTS (pelo
# menos UM chunk com embedding) para marcar o DOC INTEIRO como 'indexado'. Isso
# é falso para documentos multi-chunk parcialmente vetorizados — um doc com 60
# chunks e só 1 embedado virava "indexado" igual a um doc 100% vetorizado, e
# ficava permanentemente invisível para scripts/vetorizar_documentos.py (que só
# reprocessa docs SEM nenhum chunk embedado). Resultado real encontrado em
# produção: 26.107 chunks órfãos em docs já marcados 'indexado'.
#
# Regra corrigida: status_indexacao := 'indexado' apenas quando o doc tem PELO
# MENOS UM chunk E TODOS os seus chunks têm embedding não-nulo.
#
# Idempotente e barato (um único UPDATE). NÃO cria nem duplica chunks. NÃO
# desfaz o dano já causado por execuções anteriores da versão antiga desta
# query — para isso, ver scripts/reembedar_chunks_orfaos.py.
#
# Execução (dentro do container ejc_backend, na VPS):
#     docker exec -it ejc_backend python -m scripts.reconciliar_status_rag
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from app.core.database import AsyncSessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ejc.reconciliar_rag")


async def reconciliar() -> None:
    async with AsyncSessionLocal() as db:
        antes = (await db.execute(text(
            "SELECT status_indexacao, count(*) FROM knowledge_docs "
            "WHERE deleted_at IS NULL GROUP BY status_indexacao"
        ))).all()
        logger.info("Status ANTES: %s", {s: n for s, n in antes})

        res = await db.execute(text("""
            UPDATE knowledge_docs kd
            SET status_indexacao = 'indexado'
            WHERE kd.deleted_at IS NULL
              AND kd.status_indexacao <> 'indexado'
              AND EXISTS (
                  SELECT 1 FROM knowledge_chunks kc WHERE kc.doc_id = kd.id
              )
              AND NOT EXISTS (
                  SELECT 1 FROM knowledge_chunks kc
                  WHERE kc.doc_id = kd.id AND kc.embedding IS NULL
              )
        """))
        await db.commit()
        # rowcount pode não vir em alguns drivers async; recontamos depois.
        atualizados = getattr(res, "rowcount", None)

        depois = (await db.execute(text(
            "SELECT status_indexacao, count(*) FROM knowledge_docs "
            "WHERE deleted_at IS NULL GROUP BY status_indexacao"
        ))).all()
        logger.info("Status DEPOIS: %s", {s: n for s, n in depois})
        logger.info("Docs reconciliados para 'indexado': %s",
                    atualizados if atualizados is not None else "(rowcount indisponível)")


if __name__ == "__main__":
    asyncio.run(reconciliar())
