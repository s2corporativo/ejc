"""007 — adiciona users.custo_hora (Rentabilidade)

Aditiva e isolada: coluna nullable, sem default no banco, sem backfill.
Não afeta dados nem código existente. Reversível.

Revision ID: 007_custo_hora
Revises: 006_ingestao_rag
"""
from alembic import op
import sqlalchemy as sa

revision = "007_custo_hora"
down_revision = "006_ingestao_rag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("custo_hora", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "custo_hora")
