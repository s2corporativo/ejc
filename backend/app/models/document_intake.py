"""Persistência da Entrada Universal de Documentos."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import relationship

from app.core.database import Base


class DocumentIntakeBatch(Base):
    __tablename__ = "document_intake_batches"

    id = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=True, index=True)
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=True, index=True)
    modalidade = Column(String(64), nullable=True, index=True)
    status = Column(String(24), nullable=False, default="processando", index=True)
    nivel_prontidao = Column(String(32), nullable=True, index=True)
    document_count = Column(Integer, nullable=False, default=0)
    total_bytes = Column(Integer, nullable=False, default=0)
    resultado = Column(JSON, nullable=True)
    created_by = Column(String(36), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    items = relationship(
        "DocumentIntakeItem",
        back_populates="batch",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class DocumentIntakeItem(Base):
    __tablename__ = "document_intake_items"

    id = Column(String(36), primary_key=True)
    batch_id = Column(
        String(36), ForeignKey("document_intake_batches.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    document_id = Column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(500), nullable=False)
    extension = Column(String(16), nullable=False)
    mimetype = Column(String(100), nullable=True)
    size_bytes = Column(Integer, nullable=False, default=0)
    sha256 = Column(String(64), nullable=False, index=True)
    source_order = Column(Integer, nullable=False, default=0)
    duplicate_of_document_id = Column(String(36), nullable=True, index=True)
    extraction_status = Column(String(24), nullable=False, default="pendente", index=True)
    page_count = Column(Integer, nullable=False, default=0)
    extraction_meta = Column(JSON, nullable=True)
    classification = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    batch = relationship("DocumentIntakeBatch", back_populates="items")
