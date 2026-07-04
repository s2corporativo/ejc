"""069_api_keys — chaves de API de serviço para a API pública de conhecimento

Revision ID: 069_api_keys
Revises: 068_rag_versionamento
Create Date: 2026-07-04

Fase 2 do plano IA/RAG: integradores externos (n8n, automações) abastecem a
base de conhecimento via `POST /rag/knowledge-base/batch`, autenticados por
API key de serviço (header X-API-Key) em vez de JWT de usuário.

Tabela `api_keys`:
  - chave_hash : SHA-256 hex da chave em claro (a chave NUNCA é armazenada em
                 claro — mesmo padrão dos tokens de reset de senha).
  - prefixo    : primeiros caracteres exibíveis, para o admin reconhecer a
                 chave na listagem sem expô-la.
  - escopo     : escopos separados por vírgula (hoje: "knowledge:write").
  - client_id  : isolamento LGPD opcional — chave restrita a um cliente.
  - ativo/revoked_at/last_used_at : ciclo de vida e auditoria de uso.

ADITIVA PURA e IDEMPOTENTE (mesmo padrão da 068): CREATE TABLE IF NOT EXISTS +
índices IF NOT EXISTS. Downgrade remove a tabela (reversível).
"""
from alembic import op

revision = "069_api_keys"
down_revision = "068_rag_versionamento"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id           VARCHAR(36)  PRIMARY KEY,
            nome         VARCHAR(120) NOT NULL,
            chave_hash   VARCHAR(64)  NOT NULL,
            prefixo      VARCHAR(12)  NOT NULL,
            escopo       VARCHAR(120) NOT NULL DEFAULT 'knowledge:write',
            client_id    VARCHAR(36),
            ativo        BOOLEAN      NOT NULL DEFAULT true,
            created_at   TIMESTAMPTZ  DEFAULT now(),
            last_used_at TIMESTAMPTZ,
            revoked_at   TIMESTAMPTZ
        )
    """)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_api_keys_chave_hash ON api_keys(chave_hash)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_api_keys_client_id ON api_keys(client_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_api_keys_client_id")
    op.execute("DROP INDEX IF EXISTS ix_api_keys_chave_hash")
    op.execute("DROP TABLE IF EXISTS api_keys")
