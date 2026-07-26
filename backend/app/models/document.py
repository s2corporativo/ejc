# ── app/models/document.py ───────────────────────────────────────────────────
from __future__ import annotations
from sqlalchemy import Column, String, DateTime, Enum as SAEnum, func, Text, Integer, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum


class DocConfidencialidade(str, enum.Enum):
    normal       = "normal"
    interno      = "interno"
    restrito     = "restrito"
    confidencial = "confidencial"
    segredo_justica = "segredo_justica"


class Document(Base):
    """GED — documentos enviados (uploads). Cofre = confidencialidade >= restrito."""
    __tablename__ = "documents"

    id        = Column(String(36), primary_key=True)
    titulo    = Column(String(255), nullable=False)
    descricao = Column(Text, nullable=True)
    tipo      = Column(String(50), nullable=True)   # procuracao|contrato|decisao|peticao|prova|outro

    # Arquivo físico
    filename     = Column(String(255), nullable=False)
    filepath     = Column(String(500), nullable=False)   # caminho no volume uploads
    mimetype     = Column(String(100), nullable=True)
    size_bytes   = Column(Integer, nullable=True)
    ocr_text     = Column(Text, nullable=True)           # texto extraído (busca)
    # Integridade (DOC-022): SHA-256 (hex, 64 chars) do conteúdo na ingestão.
    # Nullable: documentos criados antes da migration 122 ficam NULL.
    sha256       = Column(String(64), nullable=True, index=True)

    confidencialidade = Column(
        SAEnum(DocConfidencialidade), nullable=False,
        default=DocConfidencialidade.normal, index=True
    )

    case_id   = Column(String(36), ForeignKey("cases.id"),   nullable=True, index=True)
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=True, index=True)
    uploaded_by = Column(String(36), nullable=True)

    # Publicação EXPLÍCITA no Portal do Cliente (DOC-049/050/SYS-064).
    # A confidencialidade é controle de COFRE interno, NÃO de publicação: um
    # documento só aparece no Portal quando portal_visible=True (fail-closed).
    # Documentos recebidos do cliente entram com portal_visible=False.
    portal_visible = Column(Boolean, nullable=False, server_default="false", index=True)
    publicado_em   = Column(DateTime(timezone=True), nullable=True)
    publicado_por  = Column(String(36), ForeignKey("users.id"), nullable=True)
    revogado_em    = Column(DateTime(timezone=True), nullable=True)
    revogado_por   = Column(String(36), ForeignKey("users.id"), nullable=True)

    # Versionamento (G3): histórico de revisões do mesmo documento.
    # versao_grupo_id agrupa todas as versões de um mesmo documento original.
    # versao é o número sequencial (1, 2, 3...); documento vigente = último criado.
    versao             = Column(Integer, nullable=False, server_default="1")
    versao_grupo_id    = Column(String(36), nullable=True, index=True)
    versao_anterior_id = Column(String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)

    # Google Drive (quando o doc vive no Drive, não no volume local)
    drive_file_id = Column(String(128), nullable=True, index=True)
    drive_link    = Column(String(500), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    case   = relationship("Case",   back_populates="documents")
    client = relationship("Client", back_populates="documents")
