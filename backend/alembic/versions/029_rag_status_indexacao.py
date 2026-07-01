"""knowledge_docs — adiciona status_indexacao (vetorização em background)

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-06-15

Suporta a geração de embeddings via FastAPI BackgroundTasks (sem Celery/Redis).
Docs existentes que já têm pelo menos um chunk vetorizado recebem 'indexado';
os demais ficam 'pendente'. O endpoint /ingest e o backfill atualizam o estado.
"""
from alembic import op
import sqlalchemy as sa

revision = "a9b0c1d2e3f4"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_docs",
        sa.Column("status_indexacao", sa.String(length=20),
                  nullable=False, server_default="pendente"),
    )
    # Docs que já têm pelo menos um chunk com embedding => marca como indexado.
    op.execute("""
        UPDATE knowledge_docs d
        SET status_indexacao = 'indexado'
        WHERE EXISTS (
            SELECT 1 FROM knowledge_chunks c
            WHERE c.doc_id = d.id AND c.embedding IS NOT NULL
        )
    """)


def downgrade() -> None:
    op.drop_column("knowledge_docs", "status_indexacao")
