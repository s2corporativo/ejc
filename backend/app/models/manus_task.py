from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Index, JSON, String, Text, func

from app.core.database import Base


class ManusTask(Base):
    """Estado auditável de uma tarefa externa Manus.

    O prompt persistido é sempre o texto já sanitizado. O resultado é aceito
    somente depois da validação do contrato estruturado pelo serviço.
    """

    __tablename__ = "manus_tasks"
    __table_args__ = (
        Index("ix_manus_tasks_user_id", "user_id"),
        Index("ix_manus_tasks_case_id", "case_id"),
        Index("ix_manus_tasks_status", "status"),
    )

    id = Column(String(36), primary_key=True)
    manus_task_id = Column(String(120), nullable=False, unique=True)
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    case_id = Column(
        String(36), ForeignKey("cases.id", ondelete="SET NULL"), nullable=True
    )
    task_type = Column(String(50), nullable=False, default="case_intelligence")
    status = Column(String(20), nullable=False, default="created")
    stop_reason = Column(String(20), nullable=True)
    prompt_sanitizado = Column(Text, nullable=False)
    resultado_json = Column(JSON, nullable=True)
    mensagem_sanitizada = Column(Text, nullable=True)
    erro_codigo = Column(String(80), nullable=True)
    erro_mensagem = Column(Text, nullable=True)
    request_id = Column(String(120), nullable=True)
    ultimo_evento_id = Column(String(160), nullable=True, unique=True)
    task_url = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
