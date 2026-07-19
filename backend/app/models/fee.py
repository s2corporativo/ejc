# ── app/models/fee.py ────────────────────────────────────────────────────────
from __future__ import annotations
from sqlalchemy import (
    Column, String, DateTime, Date, Enum as SAEnum, func, Text, Numeric,
    ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum


class FeeTipo(str, enum.Enum):
    fixo        = "fixo"
    exito       = "exito"           # percentual sobre resultado
    misto       = "misto"
    por_hora    = "por_hora"
    custas_despesas = "custas_despesas"  # reembolso de despesas
    # Adicionado ao FINAL para casar com a ordem do tipo nativo `feetipo` no
    # Postgres, onde `ALTER TYPE ... ADD VALUE` (migration 097) anexa ao fim.
    sucumbencia = "sucumbencia"     # honorários de sucumbência (CPC art. 85)


class FeeStatus(str, enum.Enum):
    pendente  = "pendente"
    pago      = "pago"
    atrasado  = "atrasado"
    cancelado = "cancelado"


class Fee(Base):
    __tablename__ = "fees"

    id     = Column(String(36), primary_key=True)
    tipo   = Column(SAEnum(FeeTipo), nullable=False, default=FeeTipo.fixo)
    status = Column(SAEnum(FeeStatus), nullable=False, default=FeeStatus.pendente, index=True)

    descricao         = Column(String(255), nullable=False)
    valor             = Column(Numeric(14, 2), nullable=True)
    percentual_exito  = Column(Numeric(5, 2),  nullable=True)
    data_vencimento   = Column(Date, nullable=True, index=True)
    data_pagamento    = Column(Date, nullable=True)

    case_id   = Column(String(36), ForeignKey("cases.id"),   nullable=True, index=True)
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False, index=True)
    observacoes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    case     = relationship("Case",   back_populates="fees")
    client   = relationship("Client", back_populates="fees")
    payments = relationship("FeePayment", back_populates="fee")


class FeePayment(Base):
    """Pagamentos parciais de um honorário."""
    __tablename__ = "fee_payments"

    id     = Column(String(36), primary_key=True)
    fee_id = Column(String(36), ForeignKey("fees.id"), nullable=False, index=True)
    valor  = Column(Numeric(14, 2), nullable=False)
    data_pagamento = Column(Date, nullable=False)
    forma  = Column(String(30), nullable=True)   # pix|transferencia|dinheiro|cartao
    comprovante_doc_id = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    fee = relationship("Fee", back_populates="payments")


class FeeCobrancaEnvio(Base):
    """Degrau da régua de cobrança ao CLIENTE já enviado para uma parcela
    (migration 084). UNIQUE(fee_id, degrau) = idempotência: no máximo um envio
    por degrau por parcela (services/cobranca_cliente_service.py).

    `degrau` ∈ {d-3, d+1, d+7, d+15, escalado_advogado} — validação de domínio
    na aplicação (VARCHAR, mesmo trade-off das tabelas raw-SQL do projeto).
    """
    __tablename__ = "fee_cobranca_envios"
    __table_args__ = (
        UniqueConstraint("fee_id", "degrau",
                         name="uq_fee_cobranca_envios_fee_degrau"),
    )

    id     = Column(String(36), primary_key=True)
    fee_id = Column(String(36), ForeignKey("fees.id"), nullable=False, index=True)
    degrau = Column(String(20), nullable=False)
    enviado_em = Column(DateTime(timezone=True), server_default=func.now())
