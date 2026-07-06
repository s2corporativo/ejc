# ── app/models/api_key.py ────────────────────────────────────────────────────
# Chaves de API de serviço (integradores externos: n8n, scripts, automações).
#
# A chave em claro NUNCA é armazenada: só o SHA-256 hex (mesmo padrão dos
# tokens de reset de senha — security_service.py). O prefixo (primeiros
# caracteres visíveis) permite ao admin identificar a chave sem expô-la.
#
# `client_id` opcional: quando preenchido, TODO conteúdo ingerido por esta
# chave é forçado ao escopo daquele cliente (isolamento LGPD — migration 055).
from __future__ import annotations

from sqlalchemy import Column, String, Boolean, DateTime, func, ForeignKey

from app.core.database import Base


class ApiKey(Base):
    __tablename__ = "api_keys"

    id         = Column(String(36), primary_key=True)
    nome       = Column(String(120), nullable=False)   # identificação humana ("n8n produção")
    # SHA-256 hex da chave em claro — lookup por igualdade exata (índice único).
    chave_hash = Column(String(64), nullable=False, unique=True, index=True)
    # Prefixo exibível ("ejc_a1b2c3…") para o admin reconhecer a chave na listagem.
    prefixo    = Column(String(12), nullable=False)
    # Escopos separados por vírgula. Hoje: "knowledge:write".
    escopo     = Column(String(120), nullable=False, server_default="knowledge:write")
    # Isolamento LGPD: chave restrita a um cliente específico (NULL = global).
    # Sem FK estrita (escopo, imposto na camada de serviço).
    client_id  = Column(String(36), nullable=True, index=True)

    ativo        = Column(Boolean, nullable=False, server_default="true")
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at   = Column(DateTime(timezone=True), nullable=True)

    def escopos(self) -> set[str]:
        return {s.strip() for s in (self.escopo or "").split(",") if s.strip()}
