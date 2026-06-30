"""051_rag_isolation — isolamento do RAG por cliente/caso (LGPD/EOAB art. 25)

Revision ID: 051_rag_isolation
Revises: 050_novos_modulos
Create Date: 2026-06-29

Adiciona client_id/case_id em knowledge_docs para que conteúdo RESTRITO (peças e
precedentes internos) só seja recuperável no escopo do próprio cliente. Conteúdo
PÚBLICO (legislação, súmulas, jurisprudência, doutrina) permanece global (NULL).

Backfill SEGURO (não-adivinhação): o indexador de peças já gravava o case_id em
`extra->>'case_id'`. Daí derivamos case_id e, via JOIN com cases, o client_id.
Idempotente (IF NOT EXISTS). Em banco já existente, popula; em banco novo (onde o
baseline já criou as colunas pelo modelo ORM), os ADD COLUMN viram no-op.
"""
from alembic import op

revision = "051_rag_isolation"
down_revision = "050_novos_modulos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE knowledge_docs ADD COLUMN IF NOT EXISTS client_id VARCHAR(36)")
    op.execute("ALTER TABLE knowledge_docs ADD COLUMN IF NOT EXISTS case_id VARCHAR(36)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_docs_client_id ON knowledge_docs(client_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_docs_case_id ON knowledge_docs(case_id)")

    # Backfill 1: case_id a partir do metadado gravado na indexação da peça.
    op.execute("""
        UPDATE knowledge_docs
        SET case_id = NULLIF(extra->>'case_id', '')
        WHERE case_id IS NULL
          AND extra ? 'case_id'
          AND NULLIF(extra->>'case_id', '') IS NOT NULL
    """)
    # Backfill 2: client_id a partir do caso (fonte autoritativa).
    op.execute("""
        UPDATE knowledge_docs kd
        SET client_id = c.client_id
        FROM cases c
        WHERE kd.case_id = c.id
          AND kd.client_id IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_docs_case_id")
    op.execute("DROP INDEX IF EXISTS ix_knowledge_docs_client_id")
    op.execute("ALTER TABLE knowledge_docs DROP COLUMN IF EXISTS case_id")
    op.execute("ALTER TABLE knowledge_docs DROP COLUMN IF EXISTS client_id")
