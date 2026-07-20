from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, Text, func

from app.core.database import Base


class AIProviderMetric(Base):
    """Telemetria técnica do gateway sem prompt, resposta ou dado pessoal.

    Cada linha representa uma tentativa real de comunicação com um provedor.
    Falhas são registradas somente pela classe do erro e eventual status HTTP;
    mensagens de exceção não são persistidas para evitar vazamento de PII ou
    detalhes de credenciais.
    """

    __tablename__ = "ai_provider_metrics"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    request_id = Column(String(36), nullable=False, index=True)
    attempt_number = Column(Integer, nullable=False, default=1)

    provider = Column(String(30), nullable=False, index=True)
    model = Column(String(160), nullable=True, index=True)
    task_type = Column(String(80), nullable=False, default="nao_informado", index=True)
    status = Column(String(20), nullable=False, index=True)  # sucesso | erro | bloqueado_lgpd

    duration_ms = Column(Integer, nullable=False, default=0)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    estimated_cost_brl = Column(Numeric(12, 6), nullable=False, default=0)

    fallback_triggered = Column(Boolean, nullable=False, default=False, index=True)
    fallback_reason = Column(Text, nullable=True)
    error_type = Column(String(100), nullable=True, index=True)
    http_status = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
