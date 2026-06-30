# ── app/models/centro_custo.py ────────────────────────────────────────────────
# Centro de Custos por Processo — lucro real por caso.
from __future__ import annotations
import enum

from sqlalchemy import (
    Column, String, Text, Numeric, Boolean,
    Date, DateTime, ForeignKey, Enum as SAEnum, func,
)
from app.core.database import Base


class CentroCustoTipo(str, enum.Enum):
    receita  = "receita"
    despesa  = "despesa"


class CentroCustoCategoria(str, enum.Enum):
    honorarios   = "honorarios"
    custas       = "custas"
    peritos      = "peritos"
    deslocamento = "deslocamento"
    documentos   = "documentos"
    diligencias  = "diligencias"
    outros       = "outros"


class CentroCusto(Base):
    __tablename__ = "centro_custos"

    id              = Column(String(36), primary_key=True)
    case_id         = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    tipo            = Column(SAEnum(CentroCustoTipo, name="centrocustotipo"), nullable=False)
    categoria       = Column(SAEnum(CentroCustoCategoria, name="centrocustocategoria"),
                             nullable=False, server_default="outros")
    valor           = Column(Numeric(15, 2), nullable=False)
    moeda           = Column(String(3), default="BRL")
    descricao       = Column(Text, nullable=False)
    data_lancamento = Column(Date, nullable=False)
    data_pagamento  = Column(Date)
    pago            = Column(Boolean, nullable=False, default=False)
    comprovante_id  = Column(String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    observacoes     = Column(Text)
    created_by      = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at      = Column(DateTime(timezone=True), nullable=True)   # soft-delete (arquitetural)
