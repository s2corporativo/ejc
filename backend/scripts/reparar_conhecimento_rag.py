#!/usr/bin/env python
"""Aprova e completa a indexação do acervo vigente da Base de Conhecimento.

A política do EJC determina que todo documento inserido no módulo de
Conhecimento esteja autorizado para uso pela inteligência jurídica. Este script
faz o backfill dos registros anteriores à política e reusa o reparador nativo de
chunks sem embedding.

Uso no container da VPS::

    python -m scripts.reparar_conhecimento_rag
    python -m scripts.reparar_conhecimento_rag --dry-run
    python -m scripts.reparar_conhecimento_rag --sem-vetorizacao
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Any

from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal
from app.models.rag import KnowledgeChunk, KnowledgeDoc
from app.services.embedding_service import disponivel as embeddings_disponiveis
from app.services.knowledge_autoapproval import aplicar_aprovacao_automatica

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ejc.reparar_conhecimento_rag")


def _precisa_reparo(doc: KnowledgeDoc) -> bool:
    extra = doc.extra or {}
    status = str(extra.get("rag_status") or "").strip().lower()
    confianca = str(
        extra.get("confidence_level") or extra.get("confianca") or ""
    ).strip().lower()
    politica = (extra.get("auto_approval") or {})
    politica_ok = isinstance(politica, dict) and (
        politica.get("policy") == "knowledge_module_always_approved"
    )
    return status != "aprovado" or confianca not in {"alta", "media", "baixa"} or not politica_ok


async def _contar_chunks_orfaos() -> int:
    async with AsyncSessionLocal() as db:
        return int((await db.execute(
            select(func.count())
            .select_from(KnowledgeChunk)
            .join(KnowledgeDoc, KnowledgeDoc.id == KnowledgeChunk.doc_id)
            .where(
                KnowledgeDoc.deleted_at.is_(None),
                KnowledgeDoc.vigente.is_(True),
                KnowledgeChunk.embedding.is_(None),
            )
        )).scalar() or 0)


async def aprovar_existentes(batch_size: int = 200, dry_run: bool = False) -> dict[str, Any]:
    """Aprova todos os documentos vigentes/não excluídos, em lotes idempotentes."""
    total = alterados = ja_conformes = 0
    after = ""

    while True:
        async with AsyncSessionLocal() as db:
            docs = (await db.execute(
                select(KnowledgeDoc)
                .where(
                    KnowledgeDoc.deleted_at.is_(None),
                    KnowledgeDoc.vigente.is_(True),
                    KnowledgeDoc.id > after,
                )
                .order_by(KnowledgeDoc.id)
                .limit(batch_size)
            )).scalars().all()

            if not docs:
                break

            for doc in docs:
                total += 1
                if _precisa_reparo(doc):
                    alterados += 1
                    if not dry_run:
                        aplicar_aprovacao_automatica(doc)
                else:
                    ja_conformes += 1

            if dry_run:
                await db.rollback()
            else:
                await db.commit()

            after = str(docs[-1].id)
            logger.info(
                "lote concluído: total=%s alterados=%s conformes=%s after=%s",
                total, alterados, ja_conformes, after,
            )

    return {
        "documentos_vigentes": total,
        "documentos_aprovados_ou_corrigidos": alterados,
        "documentos_ja_conformes": ja_conformes,
        "dry_run": dry_run,
    }


async def executar(*, batch_size: int = 200, dry_run: bool = False,
                   sem_vetorizacao: bool = False) -> dict[str, Any]:
    orfaos_antes = await _contar_chunks_orfaos()
    resumo = await aprovar_existentes(batch_size=batch_size, dry_run=dry_run)

    vetorizacao = "nao_executada"
    if not dry_run and not sem_vetorizacao:
        if embeddings_disponiveis():
            from scripts.reembedar_chunks_orfaos import reembedar
            await reembedar(batch_size=max(1, min(batch_size, 100)))
            vetorizacao = "executada"
        else:
            vetorizacao = "indisponivel"
            logger.warning(
                "Embeddings indisponíveis: documentos foram aprovados e já podem "
                "ser recuperados pelo fallback lexical; a vetorização será retomada "
                "pelo auto-reembed quando o serviço estiver disponível."
            )

    orfaos_depois = await _contar_chunks_orfaos()
    resumo.update({
        "chunks_sem_embedding_antes": orfaos_antes,
        "chunks_sem_embedding_depois": orfaos_depois,
        "vetorizacao": vetorizacao,
    })
    logger.info("reparo concluído: %s", resumo)
    return resumo


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Aprova todo conhecimento vigente e completa embeddings pendentes."
    )
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sem-vetorizacao", action="store_true")
    args = parser.parse_args()
    asyncio.run(executar(
        batch_size=max(1, args.batch_size),
        dry_run=args.dry_run,
        sem_vetorizacao=args.sem_vetorizacao,
    ))
