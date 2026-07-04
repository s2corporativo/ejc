# ── app/tasks ────────────────────────────────────────────────────────────────
# Tasks Celery (Fase 3A) + dispatcher com fallback gracioso para BackgroundTasks.
#
# IMPORTANTE: não importar rag_tasks aqui no nível de módulo — o dispatcher
# precisa ser importável mesmo sem Celery/Redis funcionais (import lazy).
from app.tasks.dispatcher import agendar_indexacao  # noqa: F401
