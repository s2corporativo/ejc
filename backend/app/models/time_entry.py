# ── app/models/time_entry.py ─────────────────────────────────────────────────
from sqlalchemy import Column, String, Integer, Boolean, Date, DateTime, func, ForeignKey
from app.core.database import Base


class TimeEntry(Base):
    __tablename__ = "time_entries"

    id        = Column(String(36), primary_key=True)
    case_id   = Column(String(36), ForeignKey("cases.id"), nullable=False, index=True)
    user_id   = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    data      = Column(Date, nullable=False)
    minutos   = Column(Integer, nullable=False)
    descricao = Column(String(500), nullable=False)
    faturavel = Column(Boolean, default=True)
    fee_id    = Column(String(36), ForeignKey("fees.id"), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
