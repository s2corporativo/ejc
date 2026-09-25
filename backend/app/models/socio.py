# ── app/models/socio.py ───────────────────────────────────────────────────────
# Gestão Societária — sócios, participação, distribuição de lucros.
from __future__ import annotations
import enum

from sqlalchemy import (
    Column, String, Text, Numeric, Boolean,
    Date, DateTime, ForeignKey, Enum as SAEnum, func,
)
from app.core.database import Base


class RegimeSocio(str, enum.Enum):
    mensalista   = "mensalista"    # pró-labore fixo mensal
    resultado    = "resultado"     # só lucros
    misto        = "misto"         # pró-labore + participação


class Socio(Base):
    __tablename__ = "socios"

    id                       = Column(String(36), primary_key=True)
    user_id                  = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"),
                                      unique=True, nullable=False)
    participacao_percentual  = Column(Numeric(5, 4), nullable=False)   # capital social; ex: 0.6000 = 60%
    resultado_percentual     = Column(Numeric(5, 4), nullable=True)    # distribuição institucional; ex: 0.3333
    regime                   = Column(SAEnum(RegimeSocio, name="regimesocio"),
                                      nullable=False, server_default="misto")
    pro_labore               = Column(Numeric(12, 2))   # mensal, se regime=mensalista|misto
    oab_numero               = Column(String(20))
    oab_uf                   = Column(String(2))
    data_entrada             = Column(Date, nullable=False)
    data_saida               = Column(Date)
    ativo                    = Column(Boolean, nullable=False, default=True)
    observacoes              = Column(Text)
    created_at               = Column(DateTime(timezone=True), server_default=func.now())
    updated_at               = Column(DateTime(timezone=True), server_default=func.now(),
                                      onupdate=func.now())


class DistribuicaoLucro(Base):
    """Registro de distribuição de lucros por mês de referência."""
    __tablename__ = "distribuicoes_lucro"

    id              = Column(String(36), primary_key=True)
    mes_referencia  = Column(String(7), nullable=False)    # YYYY-MM
    valor_total     = Column(Numeric(15, 2), nullable=False)
    socios_json     = Column(Text, nullable=False)   # JSON: [{socio_id, participacao, valor}]
    status          = Column(String(20), nullable=False, default="calculado")
    # calculado | aprovado | pago
    observacoes     = Column(Text)
    aprovado_por    = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    aprovado_em     = Column(DateTime(timezone=True))
    created_by      = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
