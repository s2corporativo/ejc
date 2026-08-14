"""Modelos do rescan/backfill de SHA-256 (Épico #1019 A3.2).

``document_hash_rescan_batches`` controla lotes de rescan (aceitação,
execução, conclusões); ``document_hash_rescan_items`` armazena o resultado
por documento, incluindo divergências (SHA ≠ intake / ausências / erros).
"""
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)

from app.core.database import Base


class DocumentHashRescanBatch(Base):
    __tablename__ = "document_hash_rescan_batches"

    id = Column(String(36), primary_key=True)
    cliente_id = Column(String(36), ForeignKey("clients.id"), nullable=True)
    caso_id = Column(String(36), ForeignKey("cases.id"), nullable=True)
    document_ids_json = Column(Text, nullable=True)
    dry_run = Column(Boolean, nullable=False, server_default="false")
    status = Column(String(20), nullable=False, server_default="pendente")
    total_selecionado = Column(Integer, nullable=True)
    total_concluidos = Column(Integer, nullable=True)
    total_erros = Column(Integer, nullable=True)
    total_nao_disponiveis = Column(Integer, nullable=True)
    mecanismo = Column(String(20), nullable=True)
    iniciado_em = Column(DateTime(timezone=True), nullable=True)
    concluido_em = Column(DateTime(timezone=True), nullable=True)
    criado_por = Column(String(36), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_doc_hash_rescan_batches_status", "status"),
    )


class DocumentHashRescanItem(Base):
    __tablename__ = "document_hash_rescan_items"

    id = Column(String(36), primary_key=True)
    batch_id = Column(String(36), nullable=False, index=True)
    document_id = Column(String(36), nullable=False, index=True)
    status = Column(String(20), nullable=False)
    motivo = Column(String(60), nullable=True)
    sha256_calculado = Column(String(64), nullable=True, index=True)
    sha256_intake = Column(String(64), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
