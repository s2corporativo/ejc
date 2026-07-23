"""117 — revisão manual de conhecimento RAG

Revision ID: 117_knowledge_revisao
Revises: 116_ai_log_risco_ia
Create Date: 2026-07-22
"""
from alembic import op
import sqlalchemy as sa

revision = "117_knowledge_revisao"
down_revision = "116_risco_ia"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_docs",
        sa.Column("revisado", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "knowledge_docs",
        sa.Column("revisado_por", sa.String(36), nullable=True),
    )
    op.add_column(
        "knowledge_docs",
        sa.Column("revisado_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_knowledge_docs_revisado", "knowledge_docs", ["revisado"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_docs_revisado", table_name="knowledge_docs")
    op.drop_column("knowledge_docs", "revisado_em")
    op.drop_column("knowledge_docs", "revisado_por")
    op.drop_column("knowledge_docs", "revisado")
