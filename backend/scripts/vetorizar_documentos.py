#!/usr/bin/env python
# ── scripts/vetorizar_documentos.py ──────────────────────────────────────────
# BUG-04: vetorização de documentos RAG que NÃO possuem chunks embedados.
#
# ATENÇÃO (produção): no diagnóstico atual, TODOS os docs já têm ≥1 chunk com
# embedding — logo este script NÃO deve processar nada. Ele existe para o caso
# de docs futuros que fiquem sem embedding (ex.: embeddings desligados na
# ingestão). O fix rotineiro é `reconciliar_status_rag.py`.
#
# Garantias:
#   • Idempotente: só processa docs SEM nenhum chunk embedado
#     (NOT EXISTS chunk com embedding) — NUNCA duplica chunks.
#   • Se o doc já tem chunks (sem embedding), embeda os chunks existentes;
#     se não tem chunk algum, gera chunks a partir de titulo+conteudo.
#     (Como knowledge_docs não guarda o texto integral, o conteúdo é
#      reconstruído a partir dos chunks existentes; se não houver chunk,
#      usa apenas o título — caso raríssimo, logado.)
#   • Commit por lote (batch_size, default 50); registra erro por doc em
#     status_indexacao='erro'; loga progresso.
#
# Execução (container ejc_backend, na VPS):
#     docker exec -it ejc_backend python -m scripts.vetorizar_documentos
#     docker exec -it ejc_backend python -m scripts.vetorizar_documentos --batch-size 25
from __future__ import annotations

import argparse
import asyncio
import logging
from uuid import uuid4

from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.rag import KnowledgeChunk
from app.services.embedding_service import gerar_embeddings, disponivel as emb_disponivel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ejc.vetorizar")


# Docs SEM nenhum chunk embedado (o conjunto "não vetorizado" de verdade).
_SQL_SEM_VETOR = text("""
    SELECT kd.id, kd.titulo
    FROM knowledge_docs kd
    WHERE kd.deleted_at IS NULL
      AND kd.status_indexacao <> 'indexado'
      AND NOT EXISTS (
          SELECT 1 FROM knowledge_chunks kc
          WHERE kc.doc_id = kd.id AND kc.embedding IS NOT NULL
      )
    ORDER BY kd.created_at
    LIMIT :limit OFFSET :offset
""")


async def _processar_doc(db: AsyncSession, doc_id: str, titulo: str) -> None:
    """Embeda os chunks de um doc. Se não houver chunk, cria a partir do título."""
    chunks = (await db.execute(
        select(KnowledgeChunk)
        .where(KnowledgeChunk.doc_id == doc_id)
        .order_by(KnowledgeChunk.chunk_index)
    )).scalars().all()

    if chunks:
        textos = [c.conteudo for c in chunks]
        vetores = await gerar_embeddings(textos)
        if not vetores:
            raise RuntimeError("gerar_embeddings retornou None")
        for ch, v in zip(chunks, vetores):
            ch.embedding = v
    else:
        # Sem chunk algum — caso raro. Usa titulo como conteúdo mínimo.
        base = (titulo or "").strip()
        if not base:
            raise RuntimeError("doc sem chunks e sem título")
        vetores = await gerar_embeddings([base])
        if not vetores:
            raise RuntimeError("gerar_embeddings retornou None")
        db.add(KnowledgeChunk(
            id=str(uuid4()), doc_id=doc_id, chunk_index=0,
            conteudo=base, embedding=vetores[0],
        ))

    await db.execute(text(
        "UPDATE knowledge_docs SET status_indexacao='indexado' WHERE id=:id"
    ), {"id": doc_id})


async def vetorizar(batch_size: int = 50) -> None:
    if not emb_disponivel():
        logger.error("Embeddings indisponíveis (EMBEDDINGS_ENABLED off ou "
                     "sentence-transformers ausente). Abortando sem alterar nada.")
        return

    total_ok = total_err = 0
    offset = 0
    while True:
        async with AsyncSessionLocal() as db:
            lote = (await db.execute(
                _SQL_SEM_VETOR, {"limit": batch_size, "offset": offset}
            )).all()
            if not lote:
                break

            for doc_id, titulo in lote:
                try:
                    await _processar_doc(db, doc_id, titulo)
                    total_ok += 1
                except Exception as e:
                    logger.warning("[vetorizar] doc %s falhou: %s", doc_id, str(e)[:200])
                    await db.execute(text(
                        "UPDATE knowledge_docs SET status_indexacao='erro' WHERE id=:id"
                    ), {"id": doc_id})
                    total_err += 1

            await db.commit()
            logger.info("[vetorizar] lote (offset=%s) commitado — ok=%s erro=%s",
                        offset, total_ok, total_err)

        # Como os processados saem do conjunto (status vira 'indexado'/'erro'),
        # não avançamos o offset para os 'ok'; mas os 'erro' permaneceriam no
        # filtro se filtrássemos só por status. Avançamos por segurança para
        # evitar loop infinito nos que viraram 'erro'.
        offset += batch_size

    logger.info("[vetorizar] concluído — vetorizados=%s, erros=%s", total_ok, total_err)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Vetoriza docs RAG sem embedding.")
    ap.add_argument("--batch-size", type=int, default=50)
    args = ap.parse_args()
    asyncio.run(vetorizar(args.batch_size))
