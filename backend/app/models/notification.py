# ── app/models/notification.py ───────────────────────────────────────────────
from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, Time, func

from app.core.database import Base


class Notification(Base):
    """Notificações internas (sino do header) + fila de WhatsApp/email."""

    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True)
    user_id = Column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )

    titulo = Column(String(255), nullable=False)
    mensagem = Column(Text, nullable=False)
    tipo = Column(
        String(30), nullable=False
    )  # prazo|honorario|sistema|ambiental|ia|diario_oficial|auditoria
    link = Column(String(255), nullable=True)  # rota no frontend

    lida = Column(Boolean, default=False, index=True)
    lida_em = Column(DateTime(timezone=True), nullable=True)

    # Canais externos
    whatsapp_enviado = Column(Boolean, default=False)
    email_enviado = Column(Boolean, default=False)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class NotificationPreference(Base):
    """Preferências pessoais; alertas jurídicos internos críticos não são silenciados."""

    __tablename__ = "notification_preferences"

    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )

    push_enabled = Column(Boolean, nullable=False, default=True)
    email_enabled = Column(Boolean, nullable=False, default=False)
    whatsapp_enabled = Column(Boolean, nullable=False, default=False)

    prazos_enabled = Column(Boolean, nullable=False, default=True)
    tarefas_enabled = Column(Boolean, nullable=False, default=True)
    intimacoes_enabled = Column(Boolean, nullable=False, default=True)
    audiencias_enabled = Column(Boolean, nullable=False, default=True)
    documentos_enabled = Column(Boolean, nullable=False, default=True)
    assinaturas_enabled = Column(Boolean, nullable=False, default=True)
    financeiro_enabled = Column(Boolean, nullable=False, default=False)
    diario_oficial_enabled = Column(Boolean, nullable=False, default=True)

    resumo_diario = Column(Boolean, nullable=False, default=False)
    quiet_hours_start = Column(Time, nullable=True)
    quiet_hours_end = Column(Time, nullable=True)
    timezone = Column(String(64), nullable=False, default="America/Sao_Paulo")

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
