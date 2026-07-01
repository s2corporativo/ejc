"""ai_logs — adiciona custo_estimado (auditoria de custo de IA)

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-06-15

Aditiva e isolada: coluna nullable, sem default no banco, sem backfill.
Ollama (local) = 0; Groq = tokens × preço por milhão (config via .env).
Não afeta dados nem código existente. Reversível.
"""
from alembic import op
import sqlalchemy as sa

revision = "f8a9b0c1d2e3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_logs",
        sa.Column("custo_estimado", sa.Numeric(12, 6), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ai_logs", "custo_estimado")
