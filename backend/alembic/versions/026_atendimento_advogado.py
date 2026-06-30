"""Atendimentos — adiciona advogado_responsavel_id e duracao_horas

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa

revision = "d6e7f8a9b0c1"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # advogado que realizou o atendimento (pode diferir de quem registrou)
    op.add_column(
        "atendimentos",
        sa.Column("advogado_responsavel_id", sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    # duração em horas decimais (ex: 1.5 = 1h30)
    op.add_column(
        "atendimentos",
        sa.Column("duracao_horas", sa.Numeric(5, 2), nullable=True),
    )
    # satisfação do cliente 1-5 (registrada após o atendimento)
    op.add_column(
        "atendimentos",
        sa.Column("satisfacao_cliente", sa.Integer, nullable=True),
    )
    op.create_index(
        "ix_atendimentos_advogado",
        "atendimentos",
        ["advogado_responsavel_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_atendimentos_advogado", table_name="atendimentos")
    op.drop_column("atendimentos", "satisfacao_cliente")
    op.drop_column("atendimentos", "duracao_horas")
    op.drop_column("atendimentos", "advogado_responsavel_id")
