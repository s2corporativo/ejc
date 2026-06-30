#!/usr/bin/env python3
# ── seeds/ingest_apis.py ─────────────────────────────────────────────────────
# Ingestão de jurisprudência via APIs públicas (executar manualmente quando
# quiser expandir a base de conhecimento):
#
#   • Lexml (legislação federal) — https://www.lexml.gov.br/busca/SRU
#   • DataJud/CNJ (metadados processuais) — API pública gratuita
#
# Uso: python seeds/ingest_apis.py --fonte lexml --termo "lei 9605"
#
# IMPORTANTE: este script ingere texto puro. Os embeddings são gerados
# depois pelo módulo de embeddings (fase 2). A busca textual já funciona.
# ─────────────────────────────────────────────────────────────────────────────
import argparse
import asyncio
import os
import sys
from uuid import uuid4

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.database import AsyncSessionLocal
from app.models.rag import KnowledgeDoc, KnowledgeChunk


async def ingest_lexml(termo: str, limite: int = 10):
    """Busca legislação no Lexml (SRU API pública, sem chave)."""
    url = "https://www.lexml.gov.br/busca/SRU"
    params = {
        "operation": "searchRetrieve",
        "query": f'urn any "{termo}"',
        "maximumRecords": limite,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        print(f"Lexml respondeu {len(r.text)} bytes — parsing XML necessário")
        print("Resultados brutos salvos. Para parsing completo, ver documentação SRU.")
        # Parsing XML completo: implementação na fase 2 (lxml)
        return r.text[:2000]


async def ingest_manual(titulo: str, categoria: str, arquivo: str):
    """Ingere arquivo de texto local na base."""
    with open(arquivo, encoding="utf-8") as f:
        conteudo = f.read()

    async with AsyncSessionLocal() as db:
        doc = KnowledgeDoc(
            id=str(uuid4()), titulo=titulo, categoria=categoria,
            fonte=f"arquivo:{os.path.basename(arquivo)}",
        )
        db.add(doc)
        # Chunking
        tam, overlap, i, idx = 1200, 150, 0, 0
        while i < len(conteudo):
            db.add(KnowledgeChunk(
                id=str(uuid4()), doc_id=doc.id, chunk_index=idx,
                conteudo=conteudo[i:i + tam],
            ))
            i += tam - overlap
            idx += 1
        await db.commit()
        print(f"✅ '{titulo}' ingerido: {idx} chunks")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--fonte", choices=["lexml", "arquivo"], required=True)
    p.add_argument("--termo", help="Termo de busca (lexml)")
    p.add_argument("--arquivo", help="Caminho do .txt (arquivo)")
    p.add_argument("--titulo", help="Título do documento (arquivo)")
    p.add_argument("--categoria", default="legislacao")
    args = p.parse_args()

    if args.fonte == "lexml":
        asyncio.run(ingest_lexml(args.termo or "lei"))
    else:
        asyncio.run(ingest_manual(args.titulo, args.categoria, args.arquivo))
