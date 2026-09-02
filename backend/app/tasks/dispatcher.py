# ── app/tasks/dispatcher.py ──────────────────────────────────────────────────
# Dispatchers de tarefas com fallback gracioso para BackgroundTasks.
#
# Celery é usado quando habilitado E Redis responde ao ping. Na ausência dessa
# infraestrutura, a request não perde a funcionalidade: a mesma função de
# domínio é registrada no BackgroundTasks do FastAPI.
from __future__ import annotations

import logging

from fastapi import BackgroundTasks

from app.core.config import get_settings

logger = logging.getLogger("ejc.tasks.dispatcher")


async def _redis_alcancavel(url: str, timeout: float = 1.0) -> bool:
    """Ping rápido no Redis. Qualquer falha (import, DNS, conexão) → False."""
    try:
        import redis.asyncio as aioredis
        cli = aioredis.from_url(
            url, socket_connect_timeout=timeout, socket_timeout=timeout
        )
        try:
            return bool(await cli.ping())
        finally:
            await cli.aclose()
    except Exception:
        return False


async def agendar_indexacao(doc_id: str, background_tasks: BackgroundTasks) -> str:
    """Agenda a vetorização de um KnowledgeDoc."""
    settings = get_settings()
    if settings.CELERY_ENABLED and await _redis_alcancavel(settings.REDIS_URL):
        try:
            from app.tasks.rag_tasks import indexar_documento_task
            indexar_documento_task.delay(doc_id)
            return "celery"
        except Exception as e:
            logger.warning(
                "[dispatcher] Celery RAG indisponível; exception_type=%s",
                type(e).__name__,
            )
    from app.routers.rag import _indexar_doc_bg
    background_tasks.add_task(_indexar_doc_bg, doc_id)
    return "background"


async def agendar_analise_documento(
    doc_id: str,
    user_id: str,
    expected_sha256: str | None,
    background_tasks: BackgroundTasks,
) -> str:
    """Agenda análise do GED sem colocar OCR/conteúdo na fila."""
    settings = get_settings()
    if settings.CELERY_ENABLED and await _redis_alcancavel(settings.REDIS_URL):
        try:
            from app.tasks.document_tasks import analisar_documento_task
            analisar_documento_task.delay(doc_id, user_id, expected_sha256)
            return "celery"
        except Exception as exc:
            logger.warning(
                "[dispatcher] Celery análise documental indisponível; exception_type=%s",
                type(exc).__name__,
            )

    from app.tasks.document_tasks import executar_analise_documento
    background_tasks.add_task(
        executar_analise_documento,
        doc_id,
        user_id,
        expected_sha256,
    )
    return "background"


async def agendar_purge_storage(
    operation_id: str,
    background_tasks: BackgroundTasks,
) -> str:
    """Agenda limpeza física da outbox após o hard purge transacional."""
    settings = get_settings()
    if settings.CELERY_ENABLED and await _redis_alcancavel(settings.REDIS_URL):
        try:
            from app.tasks.document_tasks import purge_document_storage_task
            purge_document_storage_task.delay(operation_id)
            return "celery"
        except Exception as exc:
            logger.warning(
                "[dispatcher] Celery purge storage indisponível; exception_type=%s",
                type(exc).__name__,
            )

    from app.tasks.document_tasks import executar_purge_storage
    background_tasks.add_task(executar_purge_storage, operation_id)
    return "background"
