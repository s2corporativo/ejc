"""Trocar dimensão de embeddings de 384 (MiniLM) para 768 (multilingual-e5-base)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove índices vetoriais antes de alterar o tipo
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding")

    # knowledge_chunks — sempre existe
    op.execute("UPDATE knowledge_chunks SET embedding = NULL")
    op.execute("""
        ALTER TABLE knowledge_chunks
        ALTER COLUMN embedding TYPE vector(768)
        USING NULL::vector(768)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_embedding
        ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)
    """)

    # document_chunks — pode não existir em instalações sem esse módulo
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'document_chunks'
            ) THEN
                UPDATE document_chunks SET embedding = NULL;
                ALTER TABLE document_chunks
                    ALTER COLUMN embedding TYPE vector(768)
                    USING NULL::vector(768);
                CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding
                    ON document_chunks USING hnsw (embedding vector_cosine_ops);
            END IF;
        END;
        $$;
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding")
    op.execute("UPDATE knowledge_chunks SET embedding = NULL")
    op.execute("""
        ALTER TABLE knowledge_chunks
        ALTER COLUMN embedding TYPE vector(384)
        USING NULL::vector(384)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_embedding
        ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)
    """)
