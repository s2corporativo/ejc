# ── app/tasks/dispatcher.py ──────────────────────────────────────────────────
# Dispatcher ÚNICO de indexação RAG (Fase 3A).
#
# Decide, por chamada, entre:
#   • Celery (worker dedicado)  — quando CELERY_ENABLED=True E o Redis responde;
#   • BackgroundTasks (in-process) — caso contrário (fallback gracioso, mesmo
#     espírito de embeddings/IA: infra ausente nunca quebra a request).
#
# Com CELERY_ENABLED=False (default) o comportamento é IDÊNTICO ao anterior:
# background_tasks.add_task(_indexar_doc_bg, doc_id).
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
    """Agenda a vetorização de um KnowledgeDoc. Retorna o mecanismo usado
    ("celery" | "background") — útil em testes/observabilidade."""
    settings = get_settings()
    if settings.CELERY_ENABLED and await _redis_alcancavel(settings.REDIS_URL):
        try:
            # Import lazy: dispatcher precisa funcionar sem Celery importável.
            from app.tasks.rag_tasks import indexar_documento_task
            indexar_documento_task.delay(doc_id)
            return "celery"
        except Exception as e:
            logger.warning(
                "[dispatcher] enfileirar no Celery falhou (%s: %s) — "
                "caindo para BackgroundTasks", type(e).__name__, str(e)[:200],
            )
    # Fallback / caminho padrão: mesma task in-process de antes.
    from app.routers.rag import _indexar_doc_bg
    background_tasks.add_task(_indexar_doc_bg, doc_id)
    return "background"
