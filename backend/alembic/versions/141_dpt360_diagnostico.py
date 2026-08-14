"""141 — Persistência de resultados do Diagnóstico Empresarial 360 (DPT360).

Cria a tabela `dpt_diagnosticos`, que armazena cada execução de diagnóstico
com evidências por área, estado HITL (rascunho → em_revisao → revisado →
concluido → descartado) e auditoria de quem criou e revisou.

Expand-only: nenhuma alteração em tabelas existentes.
Revision: 141_dpt360_diagnostico_persistencia
Revises: 140_preliminares_fundacao_schema
"""

from alembic import op
import sqlalchemy as sa

revision = "141_dpt360_diagnostico"
down_revision = "140_preliminares_fundacao_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dpt_diagnosticos",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("client_id", sa.String(length=36), nullable=False),
        sa.Column("tipo", sa.String(length=30), nullable=False),
        sa.Column("areas_json", sa.Text(), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("requer_revisao", sa.Boolean(), nullable=False),
        sa.Column("observacao_revisao", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("revised_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revised_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["revised_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_dpt_diagnosticos_client_id",
        "dpt_diagnosticos",
        ["client_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_dpt_diagnosticos_client_id", table_name="dpt_diagnosticos")
    op.drop_table("dpt_diagnosticos")
