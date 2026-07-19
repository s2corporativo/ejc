# ── app/models/scheduler_heartbeat.py ────────────────────────────────────────
# Heartbeat honesto dos jobs do APScheduler (achado nº 1 da auditoria:
# "monitoramento pode parar em silêncio e o painel fica verde para sempre").
#
# Uma linha por job crítico (PK = job_name). Cada execução do job faz UPSERT
# gravando `last_run_at` (quando REALMENTE rodou) e `last_status` ('ok'/'erro').
# A Central de Diagnóstico e o painel de status-captura leem esta tabela para
# detectar defasagem (job que parou de rodar) em vez de derivar saúde da última
# linha INSERIDA numa tabela de dados (que fica verde mesmo com o job morto).
from __future__ import annotations

from sqlalchemy import Column, DateTime, String, Text, func

from app.core.database import Base


class SchedulerHeartbeat(Base):
    __tablename__ = "scheduler_heartbeat"

    # job_name é o identificador canônico do job (ver heartbeat_service.JOBS_*).
    job_name    = Column(String(80), primary_key=True)
    last_run_at = Column(DateTime(timezone=True), nullable=False)
    last_status = Column(String(20), nullable=False)   # ok | erro
    detail      = Column(Text, nullable=True)          # detalhe curto do erro
    updated_at  = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
