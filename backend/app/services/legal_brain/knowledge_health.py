from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag import KnowledgeChunk, KnowledgeDoc


async def _group_count(db: AsyncSession, expression) -> dict[str, int]:
    rows = (
        await db.execute(
            select(expression.label("key"), func.count(KnowledgeDoc.id))
            .where(KnowledgeDoc.deleted_at.is_(None))
            .group_by(expression)
            .order_by(func.count(KnowledgeDoc.id).desc())
        )
    ).all()
    return {str(key if key is not None else "ausente"): int(count) for key, count in rows}


async def knowledge_health_snapshot(db: AsyncSession) -> dict[str, Any]:
    """Snapshot somente leitura da base jurídica.

    Não reclassifica vigência, não aprova documento e não executa backfill. O
    objetivo é impedir que decisões de RAG sejam tomadas sem conhecer a saúde
    real do corpus.
    """

    doc_counts = (
        await db.execute(
            select(
                func.count(KnowledgeDoc.id),
                func.count(KnowledgeDoc.id).filter(KnowledgeDoc.vigente.is_(True)),
                func.count(KnowledgeDoc.id).filter(KnowledgeDoc.vigente.is_(False)),
                func.count(KnowledgeDoc.id).filter(KnowledgeDoc.revisado.is_(True)),
                func.count(KnowledgeDoc.id).filter(
                    KnowledgeDoc.status_indexacao == "pendente"
                ),
                func.count(KnowledgeDoc.id).filter(
                    KnowledgeDoc.status_indexacao == "sem_embeddings"
                ),
            ).where(KnowledgeDoc.deleted_at.is_(None))
        )
    ).one()

    chunk_counts = (
        await db.execute(
            select(
                func.count(KnowledgeChunk.id),
                func.count(KnowledgeChunk.id).filter(KnowledgeChunk.embedding.is_(None)),
            )
        )
    ).one()

    extra = KnowledgeDoc.extra
    rag_status_expr = func.coalesce(extra["rag_status"].astext, "ausente")
    legal_status_expr = func.coalesce(extra["legal_status"].astext, "ausente")
    authority_expr = func.coalesce(extra["authority_level"].astext, "ausente")

    total, vigente, historico, revisado, indexacao_pendente, sem_embeddings_docs = (
        int(value or 0) for value in doc_counts
    )
    chunks_total, chunks_sem_embedding = (int(value or 0) for value in chunk_counts)

    return {
        "read_only": True,
        "documents": {
            "active_total": total,
            "vigente": vigente,
            "historico": historico,
            "revisado": revisado,
            "indexacao_pendente": indexacao_pendente,
            "sem_embeddings": sem_embeddings_docs,
        },
        "chunks": {
            "total": chunks_total,
            "sem_embedding": chunks_sem_embedding,
        },
        "by_category": await _group_count(db, KnowledgeDoc.categoria),
        "by_base": await _group_count(db, KnowledgeDoc.base_rag),
        "by_rag_status": await _group_count(db, rag_status_expr),
        "by_legal_status": await _group_count(db, legal_status_expr),
        "by_authority": await _group_count(db, authority_expr),
        "warnings": [
            warning
            for condition, warning in (
                (indexacao_pendente > 0, "documentos_com_indexacao_pendente"),
                (chunks_sem_embedding > 0, "chunks_sem_embedding"),
                (
                    (await _group_count(db, legal_status_expr)).get("vigencia_nao_verificada", 0) > 0,
                    "vigencia_pendente_exige_curadoria",
                ),
            )
            if condition
        ],
    }
