"""Persistência do Raio-X preliminar, isolada de clientes e casos oficiais."""
from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class RaioXAnalise(Base):
    __tablename__ = "raio_x_analises"
    __table_args__ = (
        Index("ix_raio_x_status_criado", "status", "created_at"),
        Index("ix_raio_x_criador_status", "created_by", "status"),
    )

    id = Column(String(36), primary_key=True)
    titulo = Column(String(255), nullable=False)
    potencial_cliente = Column(String(255), nullable=True)
    numero_processo = Column(String(30), nullable=True, index=True)
    area = Column(String(50), nullable=True, index=True)
    subarea = Column(String(100), nullable=True)
    rito = Column(String(100), nullable=True)
    fase = Column(String(100), nullable=True)
    tribunal = Column(String(50), nullable=True)
    orgao = Column(String(100), nullable=True)
    unidade = Column(String(100), nullable=True)
    posicao_cliente = Column(String(100), nullable=True)
    status = Column(String(40), nullable=False, default="novo", index=True)
    risco_nivel = Column(String(30), nullable=True)
    prazo_urgente = Column(Boolean, nullable=False, default=False)
    origem_contextual_case_id = Column(String(36), ForeignKey("cases.id"), nullable=True, index=True)
    convertido_case_id = Column(String(36), ForeignKey("cases.id"), nullable=True, index=True)
    dados_extraidos = Column(JSONB, nullable=False, default=dict)
    relatorio = Column(JSONB, nullable=False, default=dict)
    revisao_humana = Column(JSONB, nullable=False, default=dict)
    alertas_conflito = Column(JSONB, nullable=False, default=list)
    custo_ia = Column(JSONB, nullable=False, default=dict)
    # Memória própria da Sala de Análise Jurídica. Mantém a conversa separada da
    # revisão humana e o estado consolidado separado do relatório documental.
    conversa = Column(JSONB, nullable=False, default=list)
    estado_analise = Column(JSONB, nullable=False, default=dict)
    ultima_consolidacao_em = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    retention_until = Column(DateTime(timezone=True), nullable=True)
    converted_at = Column(DateTime(timezone=True), nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    discarded_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    documentos = relationship(
        "RaioXDocumento", back_populates="analise", cascade="all, delete-orphan",
        order_by="RaioXDocumento.created_at",
    )


class RaioXDocumento(Base):
    __tablename__ = "raio_x_documentos"
    __table_args__ = (
        UniqueConstraint("analise_id", "sha256", name="uq_raio_x_documento_hash"),
        Index("ix_raio_x_documentos_analise", "analise_id", "created_at"),
    )

    id = Column(String(36), primary_key=True)
    analise_id = Column(String(36), ForeignKey("raio_x_analises.id", ondelete="CASCADE"), nullable=False)
    nome_original = Column(String(255), nullable=False)
    filepath = Column(String(500), nullable=False)
    mimetype = Column(String(100), nullable=True)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    tipo_documento = Column(String(100), nullable=True)
    paginas = Column(Integer, nullable=True)
    ocr_utilizado = Column(Boolean, nullable=False, default=False)
    resultado_analise = Column(JSONB, nullable=False, default=dict)
    uploaded_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    analise = relationship("RaioXAnalise", back_populates="documentos")
