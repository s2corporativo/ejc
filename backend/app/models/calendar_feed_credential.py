# Credencial versionada do feed ICS pessoal.
from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func

from app.core.database import Base


class CalendarFeedCredential(Base):
    __tablename__ = "calendar_feed_credentials"

    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    version = Column(Integer, nullable=False, default=1, server_default="1")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    rotated_at = Column(DateTime(timezone=True), nullable=True)
