# ── app/models/suspensao.py ──────────────────────────────────────────────────
# Suspensões de prazo por tribunal (portarias/feriados forenses locais).
# Cobre a lacuna deixada pelo calculador nacional+municipal: cada corte (TJMG,
# TRT3, STJ, etc.) suspende prazos por atos próprios, que não são deriváveis.
from __future__ import annotations
from sqlalchemy import Column, String, Date, DateTime, func
from app.core.database import Base


class SuspensaoTribunal(Base):
    __tablename__ = "suspensoes_tribunal"

    id            = Column(String(36), primary_key=True)
    tribunal      = Column(String(40), nullable=False, index=True)   # ex: TJMG, TRT3, STJ
    data_inicio   = Column(Date, nullable=False, index=True)
    data_fim      = Column(Date, nullable=False, index=True)         # inclusivo
    motivo        = Column(String(255), nullable=False)              # ex: "Recesso forense"
    ato_normativo = Column(String(255), nullable=True)               # ex: "Portaria 1234/2026-TJMG"

    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)      # soft-delete (trilha de auditoria)
