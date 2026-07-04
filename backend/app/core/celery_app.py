# ── app/core/celery_app.py ───────────────────────────────────────────────────
# App Celery do EJC (Fase 3A — fila assíncrona real).
#
# Broker e result backend no Redis (settings.REDIS_URL). O worker roda no
# serviço `worker` do docker-compose (mesma imagem do backend):
#
#     celery -A app.core.celery_app.celery_app worker --loglevel=INFO
#
# A API só despacha para cá quando CELERY_ENABLED=True E o Redis responde ao
# ping — caso contrário o dispatcher (app/tasks/dispatcher.py) usa
# BackgroundTasks, preservando o comportamento pré-Celery.
from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "ejc",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.rag_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Sao_Paulo",
    enable_utc=True,
    # Confiabilidade: ack só depois de executar (worker morto → task re-entregue).
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Não trava o boot do worker se o Redis ainda estiver subindo (compose).
    broker_connection_retry_on_startup=True,
    # Resultados expiram em 1 dia (indexação é fire-and-forget na prática).
    result_expires=86400,
    task_default_queue="ejc",
)
