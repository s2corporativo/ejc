"""108 — credential_vault: Cofre de Credenciais (integration_credentials)

Contexto (plano em docs/PLANO_COFRE_CREDENCIAIS.md):
    Segredos de integrações externas (DataJud, Groq/Anthropic/Maritaca, Z-API,
    SMTP, NuvemFiscal, Portal da Transparência, Langfuse, VAPID...) hoje vivem
    APENAS no .env — trocar/revogar exige acesso SSH + restart. Esta tabela é o
    armazenamento cifrado em repouso do cofre: `valor_encrypted` guarda o token
    MultiFernet (VAULT_MASTER_KEYS, services/vault_crypto.py); a chave mestra
    NUNCA entra no banco.

    Versionamento por LINHA: substituir um valor cria versao+1 ativa e desativa
    a anterior zerando valor_encrypted (fica só last4 + metadados p/ auditoria).
    Unicidade do valor vigente por ÍNDICE ÚNICO PARCIAL (provider_key,
    field_key) WHERE ativo — mesmo padrão de uq_users_email_active (075).

    PR-1 (fundação): deploy INERTE — nenhum router/serviço lê ou escreve nesta
    tabela ainda (overlay no PR-2, rotas no PR-3).

ADITIVO PURO e IDEMPOTENTE: CREATE TABLE/INDEX IF NOT EXISTS; nenhuma tabela
existente é tocada (mesmo padrão raw-SQL da 107_scheduler_heartbeat).

Revision ID: 108_credential_vault
Revises: 107_scheduler_heartbeat
Create Date: 2026-07-19
"""
from alembic import op

revision = "108_credential_vault"
down_revision = "107_scheduler_heartbeat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS integration_credentials (
            id               VARCHAR(36)  PRIMARY KEY,
            provider_key     VARCHAR(50)  NOT NULL,
            field_key        VARCHAR(80)  NOT NULL,
            tipo             VARCHAR(20)  NOT NULL,
            valor_encrypted  TEXT,
            last4            VARCHAR(8),
            versao           INTEGER      NOT NULL DEFAULT 1,
            ativo            BOOLEAN      NOT NULL DEFAULT TRUE,
            origem           VARCHAR(20)  NOT NULL DEFAULT 'manual',
            expires_at       TIMESTAMPTZ,
            last_test_at     TIMESTAMPTZ,
            last_test_status VARCHAR(30),
            last_test_detail TEXT,
            created_by       VARCHAR(36)  REFERENCES users(id) ON DELETE SET NULL,
            created_at       TIMESTAMPTZ  DEFAULT now(),
            updated_at       TIMESTAMPTZ  DEFAULT now(),
            revoked_at       TIMESTAMPTZ,
            revoked_by       VARCHAR(36)  REFERENCES users(id) ON DELETE SET NULL
        )
        """
    )
    # Uma credencial VIGENTE por (provider, campo); versões desativadas ficam
    # de histórico sem violar unicidade (padrão uq_users_email_active).
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
            uq_integration_credentials_provider_field_ativo
            ON integration_credentials (provider_key, field_key)
            WHERE ativo
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_integration_credentials_provider_key
            ON integration_credentials (provider_key)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS integration_credentials")
