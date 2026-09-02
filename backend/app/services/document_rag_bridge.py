"""Ponte explícita GED -> RAG do próprio caso.

A indexação nunca cria corpus global. Documentos do GED só entram aqui quando
possuem ``client_id + case_id + ocr_text`` e o caller já comprovou ownership e
cofre. A categoria usada é a categoria já existente com isolamento simultâneo
por cliente e caso no retrieval atual; ``extra.source_kind='ged_document'``
distingue semanticamente a origem sem afrouxar ACL.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.rag import KnowledgeDoc
from app.services.ingestion_service import upsert_documento

# No retrieval atual, comunicacao_processual é fail-closed por client_id E
# case_id. Até a taxonomia RAG ganhar uma categoria canônica própria, esta é a
# única categoria existente que satisfaz o requisito de isolamento cruzado.
_CATEGORIA_CASE_SCOPED_COMPAT = "comunicacao_processual"


class DocumentRagBridgeError(RuntimeError):
    pass


async def indexar_documento_no_caso(
    db: AsyncSession,
    document: Document,
) -> tuple[KnowledgeDoc, str]:
    if document.deleted_at is not None:
        raise DocumentRagBridgeError("documento removido não pode ser indexado")
    if not document.case_id or not document.client_id:
        raise DocumentRagBridgeError("documento precisa estar vinculado a cliente e caso")
    if not document.ocr_text or len(document.ocr_text.strip()) < 50:
        raise DocumentRagBridgeError("documento sem texto suficiente para indexação")
    if not document.sha256:
        raise DocumentRagBridgeError("documento sem hash de integridade")

    grupo_id = document.versao_grupo_id or document.id
    chave = f"ged:{grupo_id}"
    extra = {
        "source_kind": "ged_document",
        "document_id": document.id,
        "document_version": int(document.versao or 1),
        "document_sha256": document.sha256,
        "confidencialidade": document.confidencialidade.value,
        # O ato de clicar 'usar na inteligência deste caso' é HITL explícito.
        "rag_status": "aprovado",
        "human_reviewed": True,
        "requires_human_review": False,
    }

    resultado = await upsert_documento(
        db,
        titulo=document.titulo,
        categoria=_CATEGORIA_CASE_SCOPED_COMPAT,
        conteudo=document.ocr_text,
        chave_origem=chave,
        fonte="ged",
        extra=extra,
        client_id=document.client_id,
        case_id=document.case_id,
        confianca="alta",
        embutir_vetores=True,
    )

    knowledge_doc = (
        await db.execute(
            select(KnowledgeDoc).where(
                KnowledgeDoc.chave_origem == chave,
                KnowledgeDoc.client_id == document.client_id,
                KnowledgeDoc.case_id == document.case_id,
                KnowledgeDoc.deleted_at.is_(None),
                KnowledgeDoc.vigente.is_(True),
            )
        )
    ).scalar_one_or_none()
    if knowledge_doc is None:
        raise DocumentRagBridgeError("RAG não retornou documento vigente")

    document.rag_knowledge_doc_id = knowledge_doc.id
    document.rag_source_sha256 = document.sha256
    document.rag_status = (
        "indexed" if knowledge_doc.status_indexacao == "indexado" else "pending"
    )
    document.rag_indexed_at = (
        datetime.now(timezone.utc) if document.rag_status == "indexed" else None
    )
    await db.commit()
    return knowledge_doc, resultado


async def desativar_rag_documento(
    db: AsyncSession,
    document: Document,
) -> bool:
    """Retira o KnowledgeDoc vigente da recuperação sem apagar histórico."""
    kd_id = document.rag_knowledge_doc_id
    if not kd_id:
        document.rag_status = "not_indexed"
        return False

    knowledge_doc = (
        await db.execute(
            select(KnowledgeDoc).where(KnowledgeDoc.id == kd_id).with_for_update()
        )
    ).scalar_one_or_none()
    if knowledge_doc is not None:
        knowledge_doc.vigente = False
        knowledge_doc.deleted_at = datetime.now(timezone.utc)
    document.rag_status = "disabled"
    document.rag_indexed_at = None
    return knowledge_doc is not None
