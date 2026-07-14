"""091 — Linha do tempo e SLA de atendimentos do cliente

Amplia a tabela existente `atendimentos` sem criar históricos paralelos:
  - registra solicitação, conclusão, prazo, prioridade e responsável;
  - vincula opcionalmente uma tarefa operacional;
  - distingue contato iniciado, confirmado ou não concluído;
  - guarda apenas o nível do último alerta para evitar notificações duplicadas.

O GED existente continua responsável pelos anexos sensíveis.

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
    op.add_column("atendimentos", sa.Column("solicitacao", sa.Text(), nullable=True))
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
    op.add_column(
        "atendimentos",
        sa.Column("solicitacao_prazo", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "atendimentos",
        sa.Column(
            "solicitacao_prioridade",
            sa.String(length=10),
            nullable=False,
            server_default="normal",
        ),
    )
    op.add_column(
        "atendimentos",
        sa.Column("solicitacao_responsavel_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "atendimentos",
        sa.Column("solicitacao_alerta_nivel", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "atendimentos",
        sa.Column("task_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "atendimentos",
        sa.Column(
            "contato_status",
            sa.String(length=20),
            nullable=False,
            server_default="confirmado",
        ),
    )

    op.create_foreign_key(
        "fk_atendimentos_atendida_por_id_users",
        "atendimentos",
        "users",
        ["atendida_por_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_atendimentos_solicitacao_responsavel_id_users",
        "atendimentos",
        "users",
        ["solicitacao_responsavel_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_atendimentos_task_id_tasks",
        "atendimentos",
        "tasks",
        ["task_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_atendimentos_client_data",
        "atendimentos",
        ["client_id", "data_atendimento"],
        unique=False,
    )
    op.create_index(
        "ix_atendimentos_solicitacao_sla",
        "atendimentos",
        ["solicitacao_atendida", "solicitacao_prazo"],
        unique=False,
    )
    op.create_index(
        "ix_atendimentos_solicitacao_responsavel_id",
        "atendimentos",
        ["solicitacao_responsavel_id"],
        unique=False,
    )
    op.create_index(
        "ix_atendimentos_task_id",
        "atendimentos",
        ["task_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_atendimentos_task_id", table_name="atendimentos")
    op.drop_index(
        "ix_atendimentos_solicitacao_responsavel_id",
        table_name="atendimentos",
    )
    op.drop_index("ix_atendimentos_solicitacao_sla", table_name="atendimentos")
    op.drop_index("ix_atendimentos_client_data", table_name="atendimentos")
    op.drop_constraint(
        "fk_atendimentos_task_id_tasks",
        "atendimentos",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_atendimentos_solicitacao_responsavel_id_users",
        "atendimentos",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_atendimentos_atendida_por_id_users",
        "atendimentos",
        type_="foreignkey",
    )
    op.drop_column("atendimentos", "contato_status")
    op.drop_column("atendimentos", "task_id")
    op.drop_column("atendimentos", "solicitacao_alerta_nivel")
    op.drop_column("atendimentos", "solicitacao_responsavel_id")
    op.drop_column("atendimentos", "solicitacao_prioridade")
    op.drop_column("atendimentos", "solicitacao_prazo")
    op.drop_column("atendimentos", "atendida_por_id")
    op.drop_column("atendimentos", "atendida_em")
    op.drop_column("atendimentos", "solicitacao_atendida")
    op.drop_column("atendimentos", "solicitacao")
