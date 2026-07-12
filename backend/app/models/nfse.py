# ── app/models/nfse.py ────────────────────────────────────────────────────────
# NFS-e emitida (ou tentada) a partir de um honorário/recebível ou avulsa.
# Persistência de verdade (não CREATE TABLE IF NOT EXISTS): migration 085.
#
# `status` como VARCHAR com validação de domínio na aplicação (NFSeStatus) —
# mesmo trade-off das migrations idempotentes 073/084 (evita ENUM nativo).
# UNIQUE(provider, referencia) = idempotência: uma nota por referência/provedor.
from __future__ import annotations

import enum

from sqlalchemy import (
    Column, String, DateTime, Text, Numeric, ForeignKey, UniqueConstraint, func,
)

from app.core.database import Base


class NFSeStatus(str, enum.Enum):
    rascunho    = "rascunho"
    processando = "processando"
    autorizada  = "autorizada"
    rejeitada   = "rejeitada"
    cancelada   = "cancelada"


class NotaFiscalServico(Base):
    __tablename__ = "notas_fiscais_servico"
    __table_args__ = (
        UniqueConstraint("provider", "referencia",
                         name="uq_notas_fiscais_servico_provider_referencia"),
    )

    id = Column(String(36), primary_key=True)

    # Origem: honorário/recebível (opcional) e cliente (opcional p/ avulsa).
    fee_id    = Column(String(36), ForeignKey("fees.id"),    nullable=True, index=True)
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=True, index=True)

    provider    = Column(String(30), nullable=False, default="nuvemfiscal")
    provider_id = Column(String(64), nullable=True, index=True)   # id da nota no provedor
    referencia  = Column(String(80), nullable=True)               # idempotência (fee-<id> | avulso-<uuid>)

    ambiente = Column(String(20), nullable=False, default="homologacao")  # homologacao|producao
    status   = Column(String(20), nullable=False, default=NFSeStatus.processando.value, index=True)

    numero       = Column(String(30),  nullable=True)
    chave_acesso = Column(String(60),  nullable=True)
    valor        = Column(Numeric(14, 2), nullable=True)
    descricao    = Column(Text, nullable=True)

    xml_url = Column(String(500), nullable=True)
    pdf_url = Column(String(500), nullable=True)

    mensagem_erro = Column(Text, nullable=True)

    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
