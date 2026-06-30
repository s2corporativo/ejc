#!/usr/bin/env python3
"""Backfill: gera embeddings para chunks existentes sem vetor.
Uso: docker compose exec backend python seeds/gerar_embeddings.py"""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.rag import KnowledgeChunk
from app.services.embedding_service import gerar_embeddings, disponivel

async def main():
    if not disponivel():
        print("❌ Ative EMBEDDINGS_ENABLED=true e instale requirements-ml.txt")
        return
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(KnowledgeChunk).where(KnowledgeChunk.embedding.is_(None))
        )).scalars().all()
        print(f"Chunks sem embedding: {len(rows)}")
        LOTE = 32
        for i in range(0, len(rows), LOTE):
            lote = rows[i:i+LOTE]
            vets = await gerar_embeddings([c.conteudo for c in lote])
            for c, v in zip(lote, vets):
                c.embedding = v
            await db.commit()
            print(f"  {min(i+LOTE, len(rows))}/{len(rows)}")
    print("✅ Backfill concluído")

asyncio.run(main())
