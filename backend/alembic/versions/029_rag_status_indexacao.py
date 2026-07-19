"""knowledge_docs — adiciona status_indexacao (vetorização em background)

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-06-15

Suporta a geração de embeddings via FastAPI BackgroundTasks (sem Celery/Redis).
Docs existentes que já têm TODOS os chunks vetorizados recebem 'indexado';
os demais ficam 'pendente'. O endpoint /ingest e o backfill atualizam o estado.

CORREÇÃO (auditoria RAG): o backfill original marcava 'indexado' com EXISTS
(pelo menos um chunk embedado) — um doc multi-chunk parcialmente vetorizado
virava "indexado" igual a um doc 100% vetorizado, e ficava invisível para
scripts de reprocessamento (que só miram docs SEM nenhum chunk embedado).
Corrigido para exigir TODOS os chunks do doc com embedding não-nulo.
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
    # Docs que já têm PELO MENOS UM chunk e TODOS os chunks com embedding =>
    # marca como indexado. NOT EXISTS (chunk sem embedding) exige unanimidade,
    # não apenas "algum" — ver correção acima.
    op.execute("""
        UPDATE knowledge_docs d
        SET status_indexacao = 'indexado'
        WHERE EXISTS (
            SELECT 1 FROM knowledge_chunks c WHERE c.doc_id = d.id
        )
        AND NOT EXISTS (
            SELECT 1 FROM knowledge_chunks c
            WHERE c.doc_id = d.id AND c.embedding IS NULL
        )
    """)


def downgrade() -> None:
    op.drop_column("knowledge_docs", "status_indexacao")
