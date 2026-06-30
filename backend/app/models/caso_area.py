# ── app/models/caso_area.py ──────────────────────────────────────────────────
# Área(s) do direito de um caso (multi-área). Model ORM para a tabela
# `caso_areas` que JÁ EXISTE. Unicidade (case_id, area) garantida no banco.
from __future__ import annotations
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.core.database import Base


class CasoArea(Base):
    __tablename__ = "caso_areas"

    id      = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    area    = Column(String(40), nullable=False)
    principal = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    case = relationship("Case", back_populates="areas")
