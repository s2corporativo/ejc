"""116 — risco_ia enum no AILog

Revision ID: 116_risco_ia
Revises: 115_case_proxima_acao
Create Date: 2026-07-22
"""
from alembic import op
import sqlalchemy as sa

revision = "116_risco_ia"
down_revision = "115_case_proxima_acao"
branch_labels = None
depends_on = None


def upgrade() -> None:
    risco_enum = sa.Enum("baixo_risco", "medio_risco", "alto_risco", name="airiscoia")
    risco_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "ai_logs",
        sa.Column("risco_ia", risco_enum, nullable=True),
    )
    op.create_index("ix_ai_logs_risco_ia", "ai_logs", ["risco_ia"])


def downgrade() -> None:
    op.drop_index("ix_ai_logs_risco_ia", table_name="ai_logs")
    op.drop_column("ai_logs", "risco_ia")
    sa.Enum(name="airiscoia").drop(op.get_bind(), checkfirst=True)
