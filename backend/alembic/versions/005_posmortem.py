"""EJC — Pós-Mortem Jurídico (ECJ): aprendizado institucional por caso

Revision ID: 005_posmortem
Revises: 004_seguranca
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa

revision = "005_posmortem"
down_revision = "004_seguranca"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("motivo_resultado", sa.Text, nullable=True))
    op.add_column("cases", sa.Column("provas_determinantes", sa.Text, nullable=True))
    op.add_column("cases", sa.Column("licoes_aprendidas", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("cases", "licoes_aprendidas")
    op.drop_column("cases", "provas_determinantes")
    op.drop_column("cases", "motivo_resultado")
