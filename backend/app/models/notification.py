# ── app/models/notification.py ───────────────────────────────────────────────
from __future__ import annotations
from sqlalchemy import Column, String, DateTime, func, Text, Boolean, ForeignKey
from app.core.database import Base


class Notification(Base):
    """Notificações internas (sino do header) + fila de WhatsApp/email."""
    __tablename__ = "notifications"

    id      = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    titulo   = Column(String(255), nullable=False)
    mensagem = Column(Text, nullable=False)
    tipo     = Column(String(30), nullable=False)   # prazo|honorario|sistema|ambiental|ia|diario_oficial|auditoria
    link     = Column(String(255), nullable=True)   # rota no frontend

    lida     = Column(Boolean, default=False, index=True)
    lida_em  = Column(DateTime(timezone=True), nullable=True)

    # Canais externos
    whatsapp_enviado = Column(Boolean, default=False)
    email_enviado    = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
