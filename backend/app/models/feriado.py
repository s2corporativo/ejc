# ── app/models/feriado.py ────────────────────────────────────────────────────
# Feriados nacionais + estaduais MG + municipais Betim.
# Móveis (Carnaval, Sexta Santa, Corpus Christi) calculados no seed por ano.
from __future__ import annotations
from sqlalchemy import Column, String, Date, Boolean
from app.core.database import Base


class Feriado(Base):
    __tablename__ = "feriados"

    id    = Column(String(36), primary_key=True)
    data  = Column(Date, nullable=False, unique=True, index=True)
    nome  = Column(String(100), nullable=False)
    tipo  = Column(String(20), nullable=False)   # nacional|estadual|municipal|forense
    movel = Column(Boolean, default=False)
