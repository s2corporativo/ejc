"""096 — embedding do RAG para vector(1024) com rollback sem perda.

Preserva a coluna 768d como ``embedding_legacy_768`` e cria a coluna 1024d vazia
(default multilingual-e5-large, suportado pelo fastembed pinado) com índice HNSW.
Os vetores anteriores permanecem disponíveis para rollback até uma migration de
limpeza posterior à validação da reindexação.

    docker exec -it ejc_backend python -m scripts.reembedar_chunks_orfaos --batch-size 20

Até o reindex concluir, o RAG usa o fallback textual. Ver o runbook. O downgrade
restaura os vetores 768d originais sem recomputá-los.

Revision ID: 096_rag_embedding_1024
Revises: 094_case_area_taxonomia
"""
from alembic import op

revision = "096_rag_embedding_1024"
down_revision = "094_case_area_taxonomia"
branch_labels = None
depends_on = None

_HNSW = "ix_knowledge_chunks_embedding_hnsw"


def upgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_HNSW}")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='knowledge_chunks' AND column_name='embedding'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='knowledge_chunks' AND column_name='embedding_legacy_768'
            ) THEN
                ALTER TABLE knowledge_chunks RENAME COLUMN embedding TO embedding_legacy_768;
            END IF;
        END $$
    """)
    op.execute("ALTER TABLE knowledge_chunks DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE knowledge_chunks ADD COLUMN embedding vector(1024)")
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {_HNSW} ON knowledge_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_HNSW}")
    op.execute("ALTER TABLE knowledge_chunks DROP COLUMN IF EXISTS embedding")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='knowledge_chunks' AND column_name='embedding_legacy_768'
            ) THEN
                ALTER TABLE knowledge_chunks RENAME COLUMN embedding_legacy_768 TO embedding;
            ELSE
                ALTER TABLE knowledge_chunks ADD COLUMN embedding vector(768);
            END IF;
        END $$
    """)
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {_HNSW} ON knowledge_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
