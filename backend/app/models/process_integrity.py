"""Persistência de proveniência processual e identidade canônica de partes."""
from __future__ import annotations

from sqlalchemy import JSON, CheckConstraint, Column, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


_JSON = JSON().with_variant(JSONB(), "postgresql")


class PartyEntity(Base):
    __tablename__ = "party_entities"
    __table_args__ = (
        CheckConstraint("entity_type IN ('PF','PJ','desconhecido')", name="ck_party_entities_type"),
        Index("ix_party_entities_normalized_name", "normalized_name"),
        Index("ix_party_entities_doc_hash", "cpf_cnpj_hash"),
        Index("ix_party_entities_client_id", "client_id"),
    )

    id = Column(String(36), primary_key=True)
    client_id = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True)
    entity_type = Column(String(16), nullable=False, server_default="desconhecido")
    display_name = Column(String(255), nullable=False)
    normalized_name = Column(String(255), nullable=False)
    cpf_cnpj_hash = Column(String(64), nullable=True)
    aliases = Column(_JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    client = relationship("Client")


class ProcessDataProvenance(Base):
    __tablename__ = "process_data_provenance"
    __table_args__ = (
        CheckConstraint("source_type IN ('usuario','documento','datajud','djen','tribunal','importacao','entrada_unica','sistema')", name="ck_process_data_provenance_source"),
        Index("ix_process_data_provenance_process", "process_id"),
        Index("ix_process_data_provenance_field", "field_name"),
        Index("ix_process_data_provenance_source", "source_type"),
    )

    id = Column(String(36), primary_key=True)
    process_id = Column(String(36), ForeignKey("processes.id", ondelete="CASCADE"), nullable=False)
    field_name = Column(String(64), nullable=False)
    source_type = Column(String(32), nullable=False)
    source_ref = Column(String(255), nullable=True)
    source_date = Column(DateTime(timezone=True), nullable=True)
    captured_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    value_snapshot = Column(_JSON, nullable=True)
    confidence = Column(String(20), nullable=True)
    confirmed_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    process = relationship("Process", back_populates="provenance")
