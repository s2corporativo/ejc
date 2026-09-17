from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint, func

from app.core.database import Base


class ActivityAlertState(Base):
    """Estado de reconhecimento do alerta por usuário.

    Não substitui o status jurídico/operacional da entidade de origem. A ausência
    de linha significa ``novo``; persistimos apenas ``visualizado``/``tratado``.
    """

    __tablename__ = "activity_alert_states"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "source_type", "source_id", name="uq_activity_alert_user_source"
        ),
    )

    id = Column(String(36), primary_key=True)
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_type = Column(String(30), nullable=False, index=True)
    source_id = Column(String(36), nullable=False, index=True)
    estado = Column(String(20), nullable=False)
    source_fingerprint = Column(String(64), nullable=True)
    visualizado_em = Column(DateTime(timezone=True), nullable=True)
    tratado_em = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
