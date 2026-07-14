"""091 — Linha do tempo de atendimentos do cliente

Amplia a tabela existente `atendimentos` sem criar um histórico paralelo:
  - solicitacao            — o que o cliente solicitou;
  - solicitacao_atendida   — estado objetivo de atendimento;
  - atendida_em            — quando a solicitação foi concluída;
  - atendida_por_id        — responsável pela conclusão.

O campo `resumo` permanece como recado/registro do atendimento. O índice
composto acelera a linha do tempo por cliente em ordem cronológica.

Alteração aditiva: registros antigos passam a pendentes apenas no sentido
técnico (`solicitacao_atendida = false`), sem fabricar uma solicitação.

Revision ID: 091_atendimento_timeline
Revises: 090_peca_versionamento
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa


revision = "091_atendimento_timeline"
down_revision = "090_peca_versionamento"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "atendimentos",
        sa.Column("solicitacao", sa.Text(), nullable=True),
    )
    op.add_column(
        "atendimentos",
        sa.Column(
            "solicitacao_atendida",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "atendimentos",
        sa.Column("atendida_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "atendimentos",
        sa.Column("atendida_por_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_atendimentos_atendida_por_id_users",
        "atendimentos",
        "users",
        ["atendida_por_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_atendimentos_client_data",
        "atendimentos",
        ["client_id", "data_atendimento"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_atendimentos_client_data", table_name="atendimentos")
    op.drop_constraint(
        "fk_atendimentos_atendida_por_id_users",
        "atendimentos",
        type_="foreignkey",
    )
    op.drop_column("atendimentos", "atendida_por_id")
    op.drop_column("atendimentos", "atendida_em")
    op.drop_column("atendimentos", "solicitacao_atendida")
    op.drop_column("atendimentos", "solicitacao")
