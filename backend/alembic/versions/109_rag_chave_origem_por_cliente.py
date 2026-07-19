"""109 — chave_origem vigente isolada por cliente no RAG.

PROBLEMA
--------
O índice vigente da migration 092 era global em `chave_origem`. Embora a camada
de recuperação já filtrasse `client_id`, a escrita não permitia que dois
clientes possuíssem a mesma chave externa e o upsert buscava sem escopo. Isso
criava risco de colisão, desativação de versão ou atualização cross-tenant.

CORREÇÃO
--------
A unicidade passa a ser `(COALESCE(client_id, ''), chave_origem)` para a versão
vigente. Documentos públicos continuam globalmente únicos porque todos usam o
mesmo escopo vazio; documentos restritos podem repetir a chave em clientes
diferentes. `case_id` permanece subescopo/metadado, pois a API de status e a
memória institucional são client-scoped.

Revision ID: 109_rag_scope_cliente
Revises: 108_credential_vault
Create Date: 2026-07-19
"""
from alembic import op

revision = "109_rag_scope_cliente"
down_revision = "108_credential_vault"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Saneamento idempotente dentro do MESMO escopo. Em base saudável é no-op.
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY COALESCE(client_id, ''), chave_origem
                       ORDER BY versao DESC NULLS LAST, atualizado_em DESC NULLS LAST, id DESC
                   ) AS rn
            FROM knowledge_docs
            WHERE chave_origem IS NOT NULL
              AND deleted_at IS NULL
              AND vigente = true
        )
        UPDATE knowledge_docs kd
           SET vigente = false
          FROM ranked
         WHERE kd.id = ranked.id
           AND ranked.rn > 1
        """
    )

    op.execute("DROP INDEX IF EXISTS uq_knowledge_docs_chave_origem_vigente")
    op.execute("DROP INDEX IF EXISTS uq_knowledge_docs_chave_origem_scope_vigente")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_knowledge_docs_chave_origem_scope_vigente
            ON knowledge_docs (COALESCE(client_id, ''), chave_origem)
         WHERE chave_origem IS NOT NULL
           AND deleted_at IS NULL
           AND vigente = true
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_knowledge_docs_chave_origem_scope_vigente")

    # O modelo antigo não representa chaves iguais em clientes diferentes. Para
    # permitir rollback sem excluir histórico, mantém vigente apenas a versão
    # mais nova globalmente e rebaixa as demais. Nenhum documento é apagado.
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY chave_origem
                       ORDER BY versao DESC NULLS LAST, atualizado_em DESC NULLS LAST, id DESC
                   ) AS rn
            FROM knowledge_docs
            WHERE chave_origem IS NOT NULL
              AND deleted_at IS NULL
              AND vigente = true
        )
        UPDATE knowledge_docs kd
           SET vigente = false
          FROM ranked
         WHERE kd.id = ranked.id
           AND ranked.rn > 1
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_knowledge_docs_chave_origem_vigente
            ON knowledge_docs (chave_origem)
         WHERE chave_origem IS NOT NULL
           AND deleted_at IS NULL
           AND vigente = true
        """
    )
