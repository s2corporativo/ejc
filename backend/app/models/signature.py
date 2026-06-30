# ── app/models/signature.py ──────────────────────────────────────────────────
# Assinatura eletrônica simples (MP 2.200-2/2001 art. 10 §2º):
# aceite registrado com hash do documento + IP + timestamp + identificação.
from sqlalchemy import Column, String, DateTime, Enum as SAEnum, func, ForeignKey
from app.core.database import Base
import enum


class SignatureStatus(str, enum.Enum):
    pendente  = "pendente"
    assinado  = "assinado"
    cancelado = "cancelado"


class SignatureRequest(Base):
    __tablename__ = "signature_requests"

    id           = Column(String(36), primary_key=True)
    document_id  = Column(String(36), ForeignKey("documents.id"), nullable=False, index=True)
    client_id    = Column(String(36), ForeignKey("clients.id"), nullable=False, index=True)
    status       = Column(SAEnum(SignatureStatus), nullable=False,
                          default=SignatureStatus.pendente, index=True)
    hash_sha256  = Column(String(64), nullable=False)
    assinado_em  = Column(DateTime(timezone=True), nullable=True)
    assinado_por_user = Column(String(36), nullable=True)
    ip           = Column(String(45), nullable=True)
    user_agent   = Column(String(300), nullable=True)
    criado_por   = Column(String(36), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
