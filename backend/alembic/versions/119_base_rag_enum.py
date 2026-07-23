"""119 — separação 3 bases RAG (G4)

Revision ID: 119_base_rag_enum
Revises: 118_doc_versionamento
Create Date: 2026-07-22
"""
from alembic import op
import sqlalchemy as sa

revision = "119_base_rag_enum"
down_revision = "118_doc_versionamento"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Criar o enum
    base_enum = sa.Enum("publica", "escritorio", "caso", name="baserag")
    base_enum.create(op.get_bind(), checkfirst=True)

    # Adicionar a coluna com default 'publica'
    op.add_column(
        "knowledge_docs",
        sa.Column("base_rag", base_enum, nullable=False, server_default="publica"),
    )
    op.create_index("ix_knowledge_docs_base_rag", "knowledge_docs", ["base_rag"])

    # Backfill: documentos com client_id não nulo → 'escritorio' ou 'caso'
    op.execute("""
        UPDATE knowledge_docs
        SET base_rag = 'caso'
        WHERE client_id IS NOT NULL AND case_id IS NOT NULL
    """)
    op.execute("""
        UPDATE knowledge_docs
        SET base_rag = 'escritorio'
        WHERE client_id IS NOT NULL AND case_id IS NULL
    """)


def downgrade() -> None:
    op.drop_index("ix_knowledge_docs_base_rag", table_name="knowledge_docs")
    op.drop_column("knowledge_docs", "base_rag")
    sa.Enum(name="baserag").drop(op.get_bind(), checkfirst=True)
