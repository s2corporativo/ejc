"""096 — embedding do RAG para vector(1024) (BGE-M3). Auditoria de IA 2026-07-17 (O-2).

Recria knowledge_chunks.embedding como vector(1024) (default BGE-M3, multilíngue)
e o índice HNSW de cosseno. A troca de dimensão é INCOMPATÍVEL com os vetores 768d
existentes (mpnet): a coluna é recriada VAZIA (NULL) e DEVE ser REINDEXADA logo
após o deploy:

    docker exec -it ejc_backend python -m scripts.reembedar_chunks_orfaos --batch-size 20

⚠️  Até o reindex concluir, o RAG usa o fallback textual (recall menor) — sem
erro. Ver RUNBOOK_MIGRACAO_EMBEDDING_1024.md. EMBEDDINGS_DIM deve casar com a
dimensão migrada; para reverter, use o downgrade (recria vector(768)) e reindexe
com o modelo antigo.

Revision ID: 096_rag_embedding_1024
Revises: 095_rag_fts_gin_index
"""
from alembic import op

revision = "096_rag_embedding_1024"
down_revision = "095_rag_fts_gin_index"
branch_labels = None
depends_on = None

_HNSW = "ix_knowledge_chunks_embedding_hnsw"


def upgrade() -> None:
    # DROP COLUMN remove automaticamente o índice vetorial dependente. A coluna
    # nova nasce NULL (o reindex regenera). Não recomputa vetores aqui.
    op.execute(f"DROP INDEX IF EXISTS {_HNSW}")
    op.execute("ALTER TABLE knowledge_chunks DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE knowledge_chunks ADD COLUMN embedding vector(1024)")
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {_HNSW} ON knowledge_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_HNSW}")
    op.execute("ALTER TABLE knowledge_chunks DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE knowledge_chunks ADD COLUMN embedding vector(768)")
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {_HNSW} ON knowledge_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
