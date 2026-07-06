# ── app/models/audit_log.py ──────────────────────────────────────────────────
# Log de auditoria IMUTÁVEL — nunca editar/deletar registros (LGPD art. 37)
from __future__ import annotations
from sqlalchemy import Column, String, DateTime, func, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base
from uuid import uuid4


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id        = Column(String(36), primary_key=True)
    user_id   = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    user_role = Column(String(30), nullable=True)
    ip        = Column(String(45), nullable=True)

    acao      = Column(String(30),  nullable=False, index=True)  # CREATE|UPDATE|DELETE|LOGIN|DOWNLOAD|AI_USE
    entidade  = Column(String(50),  nullable=False, index=True)  # cases|clients|deadlines...
    registro_id = Column(String(36), nullable=True, index=True)

    dados_antes  = Column(JSONB, nullable=True)
    dados_depois = Column(JSONB, nullable=True)
    detalhes     = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", back_populates="audit_logs")


async def criar_audit_log(
    db, user_id: str | None, user_role: str | None,
    acao: str, entidade: str, registro_id: str | None = None,
    detalhes: str | None = None, ip: str | None = None,
    dados_antes: dict | None = None, dados_depois: dict | None = None,
):
    """Helper para gravar log de auditoria. Chamado após cada operação sensível.

    Item 1.1: quando o chamador não passa `ip` (caso da maioria dos writers,
    que hoje deixavam ip=NULL), usa o IP real capturado por requisição pelo
    ClientIPMiddleware — assim CREATE/UPDATE/DELETE/UPLOAD/DOWNLOAD/CONFLITO_CHECK
    passam a registrar IP, não só o LOGIN.
    """
    if ip is None:
        from app.core.request_context import get_client_ip
        ip = get_client_ip()
    log = AuditLog(
        id=str(uuid4()), user_id=user_id, user_role=user_role,
        acao=acao, entidade=entidade, registro_id=registro_id,
        detalhes=detalhes, ip=ip,
        dados_antes=dados_antes, dados_depois=dados_depois,
    )
    db.add(log)
    # Commit pelo chamador (mesma transação da operação principal)
