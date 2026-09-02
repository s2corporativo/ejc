"""Tasks duráveis do GED: análise pós-upload e purge físico por outbox.

As mensagens da fila carregam apenas IDs/hashes, nunca OCR, título, path ou
conteúdo documental. O worker busca o conteúdo no banco sob o mesmo ambiente do
EJC e atualiza estados operacionais auditáveis.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.models.document import Document
from app.services.document_analysis_hook import analisar_documento_bg
from app.services.document_storage_operation_service import (
    StorageOperationTransientError,
    processar_operacao_storage,
)

logger = logging.getLogger("ejc.tasks.documents")


async def _com_engine_limpo(coro):
    from app.core.database import engine
    try:
        return await coro
    finally:
        await engine.dispose()


async def executar_analise_documento(
    doc_id: str,
    user_id: str,
    expected_sha256: str | None,
) -> str:
    """Executa análise somente da versão/hash que foi efetivamente agendada."""

    async with AsyncSessionLocal() as db:
        document = (
            await db.execute(
                select(Document).where(
                    Document.id == doc_id,
                    Document.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if document is None:
            return "missing"

        if expected_sha256 and document.sha256 != expected_sha256:
            document.analysis_status = "stale"
            document.analysis_error_code = "source_changed"
            document.analysis_updated_at = datetime.now(timezone.utc)
            document.analysis_source_sha256 = expected_sha256
            await db.commit()
            return "stale"

        if not document.case_id or not document.ocr_text:
            document.analysis_status = "not_requested"
            document.analysis_error_code = None
            document.analysis_updated_at = datetime.now(timezone.utc)
            await db.commit()
            return "not_requested"

        case_id = document.case_id
        ocr_text = document.ocr_text
        source_sha = document.sha256
        document.analysis_status = "processing"
        document.analysis_error_code = None
        document.analysis_updated_at = datetime.now(timezone.utc)
        document.analysis_source_sha256 = source_sha
        await db.commit()

        try:
            await analisar_documento_bg(
                case_id,
                ocr_text,
                doc_id,
                user_id,
                raise_on_error=True,
            )
        except Exception:
            document.analysis_status = "failed"
            document.analysis_error_code = "analysis_failed"
            document.analysis_updated_at = datetime.now(timezone.utc)
            await db.commit()
            raise

        document.analysis_status = "completed"
        document.analysis_error_code = None
        document.analysis_updated_at = datetime.now(timezone.utc)
        document.analysis_source_sha256 = source_sha
        await db.commit()
        return "completed"


@celery_app.task(
    name="app.tasks.analisar_documento_ged",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def analisar_documento_task(
    self,
    doc_id: str,
    user_id: str,
    expected_sha256: str | None = None,
) -> str:
    try:
        return asyncio.run(
            _com_engine_limpo(
                executar_analise_documento(doc_id, user_id, expected_sha256)
            )
        )
    except Exception:
        logger.warning("Análise GED falhou; doc_id=%s", doc_id)
        raise self.retry(exc=RuntimeError("document_analysis_failed"))


async def executar_purge_storage(operation_id: str) -> str:
    return await processar_operacao_storage(operation_id)


@celery_app.task(
    name="app.tasks.purge_document_storage",
    bind=True,
    max_retries=5,
    default_retry_delay=120,
)
def purge_document_storage_task(self, operation_id: str) -> str:
    try:
        return asyncio.run(
            _com_engine_limpo(executar_purge_storage(operation_id))
        )
    except StorageOperationTransientError:
        logger.warning("Purge físico pendente de retry; operation_id=%s", operation_id)
        raise self.retry(exc=RuntimeError("document_storage_unavailable"))
    except Exception:
        logger.error("Purge físico falhou; operation_id=%s", operation_id)
        raise self.retry(exc=RuntimeError("document_storage_failed"))
