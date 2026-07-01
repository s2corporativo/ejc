"""Gestão Societária — sócios e distribuição de lucros

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

revision = "a3b4c5d6e7f8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE regimesocio AS ENUM ('mensalista','resultado','misto');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END 
        $$
    """)

    op.create_table(
        "socios",
        sa.Column("id",                      sa.String(36), primary_key=True),
        sa.Column("user_id",                 sa.String(36),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), unique=True, nullable=False),
        sa.Column("participacao_percentual", sa.Numeric(5, 4), nullable=False),
        sa.Column("regime",                  PG_ENUM("mensalista","resultado","misto",
                                                     name="regimesocio", create_type=False),
                  nullable=False, server_default="misto"),
        sa.Column("pro_labore",              sa.Numeric(12, 2)),
        sa.Column("oab_numero",              sa.String(20)),
        sa.Column("oab_uf",                  sa.String(2)),
        sa.Column("data_entrada",            sa.Date, nullable=False),
        sa.Column("data_saida",              sa.Date),
        sa.Column("ativo",                   sa.Boolean, nullable=False, server_default="true"),
        sa.Column("observacoes",             sa.Text),
        sa.Column("created_at",              sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at",              sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "distribuicoes_lucro",
        sa.Column("id",             sa.String(36), primary_key=True),
        sa.Column("mes_referencia", sa.String(7),  nullable=False),   # YYYY-MM
        sa.Column("valor_total",    sa.Numeric(15, 2), nullable=False),
        sa.Column("socios_json",    sa.Text, nullable=False),
        sa.Column("status",         sa.String(20), nullable=False, server_default="calculado"),
        sa.Column("observacoes",    sa.Text),
        sa.Column("aprovado_por",   sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("aprovado_em",    sa.DateTime(timezone=True)),
        sa.Column("created_by",     sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at",     sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_dist_lucro_mes", "distribuicoes_lucro", ["mes_referencia"])


def downgrade() -> None:
    op.drop_table("distribuicoes_lucro")
    op.drop_table("socios")
    op.execute("DROP TYPE IF EXISTS regimesocio")
