# ── app/models/document.py ───────────────────────────────────────────────────
from __future__ import annotations
from sqlalchemy import Column, String, DateTime, Enum as SAEnum, func, Text, Integer, ForeignKey
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
    tipo      = Column(String(50), nullable=True)

    filename     = Column(String(255), nullable=False)
    filepath     = Column(String(500), nullable=False)
    mimetype     = Column(String(100), nullable=True)
    size_bytes   = Column(Integer, nullable=True)
    ocr_text     = Column(Text, nullable=True)

    confidencialidade = Column(
        SAEnum(DocConfidencialidade), nullable=False,
        default=DocConfidencialidade.normal, index=True
    )

    case_id   = Column(String(36), ForeignKey("cases.id"), nullable=True, index=True)
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=True, index=True)
    uploaded_by = Column(String(36), nullable=True)

    drive_file_id = Column(String(128), nullable=True, index=True)
    drive_link    = Column(String(500), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    case   = relationship("Case", back_populates="documents")
    client = relationship("Client", back_populates="documents")

    @property
    def nome_arquivo(self) -> str:
        """Alias semântico somente de leitura para a coluna física `filename`."""
        return self.filename
