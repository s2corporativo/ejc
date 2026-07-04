---
name: orquestrador-celery-redis
description: >
  Implementa filas de tarefas assíncronas com Celery + Redis para os sistemas EJC e S2. Use quando o volume de tarefas em background justificar migração do APScheduler para Celery: envio de emails em fila, geração de PDFs pesados, sincronização com tribunais, radar de editais agendado, processamento de OCR, relatórios gerenciais. Diferença: arquiteto-notificacoes usa APScheduler (simples, embutido); este skill configura Celery (distribuído, escalável, com retry e monitoramento via Flower). Stack: Celery 5+ + Redis + Flower (dashboard). Acionado por: "Celery", "fila de tarefas", "task queue", "Redis fila", "processamento assíncrono EJC", "worker background", "Flower monitoramento", "Celery beat", "tarefa em background escalável", "migrar APScheduler para Celery".
---

# Orquestrador Celery + Redis — EJC e S2

## Quando usar Celery vs APScheduler

```
APScheduler (arquiteto-notificacoes) → MVP, volume baixo, 1 servidor, simples
Celery + Redis → Volume médio/alto, múltiplos workers, retry, monitoramento, distribuído
```

## docker-compose.yml additions

```yaml
redis:
  image: redis:7-alpine
  restart: unless-stopped
  volumes:
    - redis_data:/data
  command: redis-server --appendonly yes

celery-worker:
  build: ./backend
  command: celery -A app.celery_app worker --loglevel=info --concurrency=4
  environment:
    - CELERY_BROKER_URL=redis://redis:6379/0
    - CELERY_RESULT_BACKEND=redis://redis:6379/1
    - DATABASE_URL=${DATABASE_URL}
  depends_on: [redis, db]
  restart: unless-stopped

celery-beat:
  build: ./backend
  command: celery -A app.celery_app beat --loglevel=info
  environment:
    - CELERY_BROKER_URL=redis://redis:6379/0
  depends_on: [redis]
  restart: unless-stopped

flower:
  image: mher/flower:2.0
  command: celery --broker=redis://redis:6379/0 flower --port=5555
  ports: ["5555:5555"]
  depends_on: [redis]
  restart: unless-stopped

volumes:
  redis_data:
```

## celery_app.py

```python
# backend/app/celery_app.py
from celery import Celery
from celery.schedules import crontab
import os

celery_app = Celery(
    "ejc",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
    include=["app.tasks.notifications", "app.tasks.tribunal", "app.tasks.reports"]
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="America/Sao_Paulo",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# Tarefas agendadas (Beat)
celery_app.conf.beat_schedule = {
    "check-deadlines-morning": {
        "task": "app.tasks.notifications.check_critical_deadlines",
        "schedule": crontab(hour=8, minute=0, day_of_week="mon-fri"),
    },
    "radar-pncp": {
        "task": "app.tasks.radar.run_pncp_radar",
        "schedule": crontab(hour="7,14", minute=0, day_of_week="mon-fri"),
    },
    "monthly-billing-verde-limp": {
        "task": "app.tasks.billing.run_monthly_billing",
        "schedule": crontab(hour=9, minute=0, day_of_month=1),
    },
}
```

## Exemplo de Task

```python
# backend/app/tasks/notifications.py
from app.celery_app import celery_app
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_deadline_alert(self, deadline_id: int):
    try:
        from app.database import SessionLocal
        db = SessionLocal()
        # ... lógica de envio
        db.close()
    except Exception as exc:
        logger.error(f"Deadline alert failed: {exc}")
        raise self.retry(exc=exc)

@celery_app.task
def check_critical_deadlines():
    """Executada pelo Beat diariamente"""
    from app.database import SessionLocal
    db = SessionLocal()
    # query deadlines críticos → disparar send_deadline_alert.delay(id)
    db.close()
```
