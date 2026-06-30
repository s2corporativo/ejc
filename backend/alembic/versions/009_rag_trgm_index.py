"""009 — índice GIN trigram em knowledge_chunks.conteudo (busca textual RAG)

Acelera o fallback ILIKE da busca da base de conhecimento (sem embeddings),
que antes fazia varredura sequencial. Aditiva e reversível.

Revision ID: 009_rag_trgm_index
Revises: 008_suspensoes_tribunal
"""
from alembic import op

revision = "009_rag_trgm_index"
down_revision = "008_suspensoes_tribunal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_conteudo_trgm "
        "ON knowledge_chunks USING gin (conteudo gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_conteudo_trgm")
