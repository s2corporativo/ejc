# ── app/models/nfse.py ───────────────────────────────────────────────────────
from __future__ import annotations

import enum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)

from app.core.database import Base


class NFSeStatus(str, enum.Enum):
    rascunho = "rascunho"
    processando = "processando"
    autorizada = "autorizada"
    rejeitada = "rejeitada"
    cancelada = "cancelada"


class NotaFiscalServico(Base):
    __tablename__ = "notas_fiscais_servico"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "referencia",
            name="uq_notas_fiscais_servico_provider_referencia",
        ),
    )

    id = Column(String(36), primary_key=True)
    fee_id = Column(String(36), ForeignKey("fees.id"), nullable=True, index=True)
    client_id = Column(
        String(36), ForeignKey("clients.id"), nullable=True, index=True
    )

    provider = Column(String(30), nullable=False, default="nuvemfiscal")
    provider_id = Column(String(64), nullable=True, index=True)
    referencia = Column(String(80), nullable=True)

    ambiente = Column(String(20), nullable=False, default="homologacao")
    status = Column(
        String(20),
        nullable=False,
        default=NFSeStatus.processando.value,
        index=True,
    )

    numero = Column(String(30), nullable=True)
    chave_acesso = Column(String(60), nullable=True)
    valor = Column(Numeric(14, 2), nullable=True)
    descricao = Column(Text, nullable=True)

    data_emissao = Column(Date, nullable=True)
    competencia = Column(Date, nullable=True)
    motivo_cancelamento = Column(Text, nullable=True)

    # Prova da natureza do cancelamento. `status=cancelada` sozinho não basta:
    # no provider=manual ele significa apenas que o EJC encerrou o REGISTRO
    # local de uma nota que foi emitida fora do sistema.
    cancelamento_tipo = Column(String(30), nullable=True)  # registro_local|fiscal_provider
    cancelamento_fiscal_confirmado = Column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    cancelamento_confirmado_em = Column(DateTime(timezone=True), nullable=True)

    pdf_path = Column(String(500), nullable=True)
    xml_path = Column(String(500), nullable=True)
    xml_url = Column(String(500), nullable=True)
    pdf_url = Column(String(500), nullable=True)
    mensagem_erro = Column(Text, nullable=True)

    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
