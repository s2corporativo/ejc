"""Monitor de Diários Oficiais — keywords e alertas

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "diario_oficial_keywords",
        sa.Column("id",         sa.String(36), primary_key=True),
        sa.Column("keyword",    sa.String(200), nullable=False),
        sa.Column("fonte",      sa.String(20),  nullable=False, server_default="dou"),
        sa.Column("ativo",      sa.Boolean, nullable=False, server_default="true"),
        sa.Column("case_id",    sa.String(36),
                  sa.ForeignKey("cases.id",  ondelete="SET NULL"), nullable=True),
        sa.Column("created_by", sa.String(36),
                  sa.ForeignKey("users.id",  ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "diario_oficial_alertas",
        sa.Column("id",              sa.String(36), primary_key=True),
        sa.Column("fonte",           sa.String(20), nullable=False),
        sa.Column("edicao",          sa.String(30)),
        sa.Column("data_publicacao", sa.Date),
        sa.Column("secao",           sa.String(10)),
        sa.Column("titulo",          sa.String(500)),
        sa.Column("resumo",          sa.Text),
        sa.Column("link",            sa.Text),
        sa.Column("keyword_match",   sa.String(200)),
        sa.Column("keyword_id",      sa.String(36),
                  sa.ForeignKey("diario_oficial_keywords.id", ondelete="SET NULL"), nullable=True),
        sa.Column("lido",            sa.Boolean, nullable=False, server_default="false"),
        sa.Column("case_id",         sa.String(36),
                  sa.ForeignKey("cases.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at",      sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_dou_alertas_data",  "diario_oficial_alertas", ["data_publicacao"])
    op.create_index("ix_dou_alertas_lido",  "diario_oficial_alertas", ["lido"])


def downgrade() -> None:
    op.drop_table("diario_oficial_alertas")
    op.drop_table("diario_oficial_keywords")
