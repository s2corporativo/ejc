from sqlalchemy import Column, String, Boolean, DateTime, func, ForeignKey
from app.core.database import Base

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    id             = Column(String(36), primary_key=True)
    user_id        = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    token_hash     = Column(String(64), nullable=False, unique=True, index=True)
    used           = Column(Boolean, default=False)
    expires_at     = Column(DateTime(timezone=True), nullable=False)
    ip_solicitante = Column(String(45))
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

class UserKnownIP(Base):
    __tablename__ = "user_known_ips"
    id               = Column(String(36), primary_key=True)
    user_id          = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    ip               = Column(String(45), nullable=False)
    user_agent_hash  = Column(String(16))
    primeira_vez_em  = Column(DateTime(timezone=True), server_default=func.now())
