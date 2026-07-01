"""008 — cria suspensoes_tribunal (suspensão de prazo por tribunal)

Aditiva e isolada: nova tabela, não altera nada existente. Reversível.

Revision ID: 008_suspensoes_tribunal
Revises: 007_custo_hora
"""
from alembic import op
import sqlalchemy as sa

revision = "008_suspensoes_tribunal"
down_revision = "007_custo_hora"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "suspensoes_tribunal",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tribunal", sa.String(40), nullable=False),
        sa.Column("data_inicio", sa.Date(), nullable=False),
        sa.Column("data_fim", sa.Date(), nullable=False),
        sa.Column("motivo", sa.String(255), nullable=False),
        sa.Column("ato_normativo", sa.String(255), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_suspensoes_tribunal_tribunal", "suspensoes_tribunal", ["tribunal"])
    op.create_index("ix_suspensoes_tribunal_data_inicio", "suspensoes_tribunal", ["data_inicio"])
    op.create_index("ix_suspensoes_tribunal_data_fim", "suspensoes_tribunal", ["data_fim"])


def downgrade() -> None:
    op.drop_index("ix_suspensoes_tribunal_data_fim", table_name="suspensoes_tribunal")
    op.drop_index("ix_suspensoes_tribunal_data_inicio", table_name="suspensoes_tribunal")
    op.drop_index("ix_suspensoes_tribunal_tribunal", table_name="suspensoes_tribunal")
    op.drop_table("suspensoes_tribunal")
