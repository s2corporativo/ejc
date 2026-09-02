# ── app/core/celery_app.py ───────────────────────────────────────────────────
# App Celery do EJC (Fase 3A).
#
# Broker e result backend no Redis (settings.REDIS_URL). O worker roda no
# serviço `worker` do docker-compose (mesma imagem do backend):
#
#     celery -A app.core.celery_app.celery_app worker --loglevel=INFO
#
# A API só despacha para cá quando CELERY_ENABLED=True E o Redis responde ao
# ping — caso contrário os dispatchers usam BackgroundTasks.
from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "ejc",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.rag_tasks",
        "app.tasks.document_tasks",
        "app.tasks.rescan_tasks",
        "app.tasks.vault_sync",
        "app.tasks.processo_eletronico_tasks",
        "app.tasks.raio_x_tasks",
        # event_subscribers instala o registro único de providers e a telemetria
        # também dentro do processo worker.
        "app.services.event_subscribers",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Sao_Paulo",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    result_expires=86400,
    task_default_queue="ejc",
)
