"""Centro de Custos — adiciona soft-delete (deleted_at)

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-06-15

Alinha centro_custos ao padrão arquitetural de soft-delete (igual a cases,
clients, documents, etc.). Lançamentos financeiros nunca devem ser apagados
fisicamente — passam a ser marcados com deleted_at e excluídos das queries.
Aditiva, reversível, sem backfill.
"""
from alembic import op
import sqlalchemy as sa

revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "centro_custos",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("centro_custos", "deleted_at")
