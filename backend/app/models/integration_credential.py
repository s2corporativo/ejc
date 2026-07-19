# ── app/models/integration_credential.py ─────────────────────────────────────
# Cofre de Credenciais — segredos de integrações externas cifrados em repouso
# (MultiFernet com VAULT_MASTER_KEYS, ver services/vault_crypto.py). Persistência
# de verdade: migration 108 (CREATE TABLE IF NOT EXISTS, padrão da 107).
#
# Modelo de versionamento: cada substituição de valor cria uma LINHA nova com
# versao+1 e desativa a anterior (ativo=False + valor_encrypted=NULL — o
# segredo antigo é ZERADO, não fica de histórico; sobra só last4 + metadados
# para auditoria). Unicidade do valor vigente é imposta por ÍNDICE ÚNICO
# PARCIAL (provider_key, field_key) WHERE ativo — mesmo padrão de
# uq_users_email_active (075).
#
# `tipo`/`origem`/`last_test_status` como VARCHAR com domínio validado na
# aplicação (evita ENUM nativo — mesmo trade-off da 107/nfse):
#   tipo   ∈ api_key | token | login | senha | oauth_client (credential_registry)
#   origem ∈ manual | env_import
#   last_test_status ∈ configurada | ausente | invalida | expirada |
#                      sem_permissao | indisponivel (PR-4)
from __future__ import annotations

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, func,
    text,
)

from app.core.database import Base


class IntegrationCredential(Base):
    __tablename__ = "integration_credentials"
    __table_args__ = (
        Index(
            "uq_integration_credentials_provider_field_ativo",
            "provider_key", "field_key",
            unique=True,
            postgresql_where=text("ativo"),
            # Mesmo índice parcial no SQLite (suíte de testes/aiosqlite) —
            # sem isto o SQLite criaria um UNIQUE cheio e proibiria o
            # histórico de versões desativadas.
            sqlite_where=text("ativo"),
        ),
    )

    id = Column(String(36), primary_key=True)  # UUID string

    # Identidade do campo no catálogo (services/credential_registry.py).
    # field_key = nome EXATO do atributo em Settings (ex.: "DATAJUD_API_KEY")
    # — é o contrato que permite ao overlay (PR-2) fazer setattr no singleton.
    provider_key = Column(String(50), nullable=False, index=True)
    field_key    = Column(String(80), nullable=False)
    tipo         = Column(String(20), nullable=False)

    # Segredo cifrado (vault_crypto.cifrar). NULL quando a versão foi
    # substituída/revogada (valor antigo zerado de propósito).
    valor_encrypted = Column(Text, nullable=True)
    last4           = Column(String(8), nullable=True)  # sufixo exibível na UI
    versao          = Column(Integer, nullable=False, default=1)
    ativo           = Column(Boolean, nullable=False, default=True)
    origem          = Column(String(20), nullable=False, default="manual")

    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Último teste da integração (PR-4) — estado retrocompatível do painel.
    last_test_at     = Column(DateTime(timezone=True), nullable=True)
    last_test_status = Column(String(30), nullable=True)
    last_test_detail = Column(Text, nullable=True)

    created_by = Column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoked_by = Column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
