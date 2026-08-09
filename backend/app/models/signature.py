# ── app/models/signature.py ──────────────────────────────────────────────────
# Assinatura eletrônica simples/avançada conforme a evidência disponível:
# aceite autenticado + hash SHA-256 do documento + IP + UA + timestamp.
from __future__ import annotations

import enum

from sqlalchemy import (
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)

from app.core.database import Base


class SignatureStatus(str, enum.Enum):
    pendente = "pendente"
    assinado = "assinado"
    cancelado = "cancelado"


class SignatureSignerStatus(str, enum.Enum):
    pendente = "pendente"
    assinado = "assinado"
    recusado = "recusado"


class SignatureRequest(Base):
    __tablename__ = "signature_requests"

    id = Column(String(36), primary_key=True)
    document_id = Column(
        String(36), ForeignKey("documents.id"), nullable=False, index=True
    )
    client_id = Column(
        String(36), ForeignKey("clients.id"), nullable=False, index=True
    )
    status = Column(
        SAEnum(SignatureStatus),
        nullable=False,
        default=SignatureStatus.pendente,
        index=True,
    )
    hash_sha256 = Column(String(64), nullable=False)

    assinado_em = Column(DateTime(timezone=True), nullable=True)
    assinado_por_user = Column(String(36), nullable=True)
    ip = Column(String(45), nullable=True)
    user_agent = Column(String(300), nullable=True)
    criado_por = Column(String(36), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)


class SignatureSigner(Base):
    """Signatário obrigatório de uma solicitação de assinatura."""

    __tablename__ = "signature_signers"
    __table_args__ = (
        UniqueConstraint(
            "signature_request_id",
            "user_id",
            name="uq_signature_signers_request_user",
        ),
    )

    id = Column(String(36), primary_key=True)
    signature_request_id = Column(
        String(36),
        ForeignKey("signature_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    nome_snapshot = Column(String(255), nullable=True)
    email_snapshot = Column(String(320), nullable=False)
    papel_snapshot = Column(String(80), nullable=False, default="cliente")
    status = Column(
        SAEnum(
            SignatureSignerStatus,
            native_enum=False,
            create_constraint=True,
            length=20,
            name="ck_signature_signers_status_enum",
        ),
        nullable=False,
        default=SignatureSignerStatus.pendente,
        index=True,
    )
    assinado_em = Column(DateTime(timezone=True), nullable=True)
    ip = Column(String(45), nullable=True)
    user_agent = Column(String(300), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
