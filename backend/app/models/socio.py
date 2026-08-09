# ── app/models/socio.py ──────────────────────────────────────────────────────
from __future__ import annotations

import enum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)

from app.core.database import Base


class RegimeSocio(str, enum.Enum):
    mensalista = "mensalista"
    resultado = "resultado"
    misto = "misto"


class Socio(Base):
    __tablename__ = "socios"

    id = Column(String(36), primary_key=True)
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    participacao_percentual = Column(Numeric(5, 4), nullable=False)
    regime = Column(
        SAEnum(RegimeSocio, name="regimesocio"),
        nullable=False,
        server_default="misto",
    )
    pro_labore = Column(Numeric(12, 2))
    oab_numero = Column(String(20))
    oab_uf = Column(String(2))
    data_entrada = Column(Date, nullable=False)
    data_saida = Column(Date)
    ativo = Column(Boolean, nullable=False, default=True)
    observacoes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SocioHistorico(Base):
    """Snapshot imutável das mutações do quadro societário.

    Não substitui contrato social/Junta Comercial; serve como trilha interna do
    EJC para demonstrar quem alterou participação, pró-labore, regime e estado.
    """

    __tablename__ = "socios_historico"

    id = Column(String(36), primary_key=True)
    socio_id = Column(
        String(36), ForeignKey("socios.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    alterado_por = Column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    motivo = Column(Text, nullable=False)
    dados_antes = Column(Text, nullable=True)
    dados_depois = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class DistribuicaoLucro(Base):
    __tablename__ = "distribuicoes_lucro"

    id = Column(String(36), primary_key=True)
    mes_referencia = Column(String(7), nullable=False)
    valor_total = Column(Numeric(15, 2), nullable=False)
    socios_json = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="calculado")
    observacoes = Column(Text)
    aprovado_por = Column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    aprovado_em = Column(DateTime(timezone=True))
    created_by = Column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
