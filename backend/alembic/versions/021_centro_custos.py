"""Centro de Custos por Processo — lucro real por caso

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for enum_name, values in [
        ("centrocustotipo",      ["receita","despesa"]),
        ("centrocustocategoria", ["honorarios","custas","peritos","deslocamento","documentos","diligencias","outros"]),
    ]:
        vals = ",".join(f"'{v}'" for v in values)
        op.execute(f"""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{enum_name}') THEN
                    CREATE TYPE {enum_name} AS ENUM ({vals});
                END IF;
            END $$
        """)

    op.create_table(
        "centro_custos",
        sa.Column("id",              sa.String(36), primary_key=True),
        sa.Column("case_id",         sa.String(36),
                  sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tipo",            PG_ENUM("receita","despesa", name="centrocustotipo", create_type=False),
                  nullable=False),
        sa.Column("categoria",       PG_ENUM("honorarios","custas","peritos","deslocamento",
                                             "documentos","diligencias","outros",
                                             name="centrocustocategoria", create_type=False),
                  nullable=False, server_default="outros"),
        sa.Column("valor",           sa.Numeric(15, 2), nullable=False),
        sa.Column("moeda",           sa.String(3), server_default="BRL"),
        sa.Column("descricao",       sa.Text, nullable=False),
        sa.Column("data_lancamento", sa.Date, nullable=False),
        sa.Column("data_pagamento",  sa.Date),
        sa.Column("pago",            sa.Boolean, nullable=False, server_default="false"),
        sa.Column("comprovante_id",  sa.String(36),
                  sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("observacoes",     sa.Text),
        sa.Column("created_by",      sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at",      sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at",      sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_centro_custos_case",      "centro_custos", ["case_id"])
    op.create_index("ix_centro_custos_lancamento","centro_custos", ["data_lancamento"])


def downgrade() -> None:
    op.drop_table("centro_custos")
    op.execute("DROP TYPE IF EXISTS centrocustotipo")
    op.execute("DROP TYPE IF EXISTS centrocustocategoria")
