"""Dossiê Estratégico — snapshots versionados por caso

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

revision = "c5d6e7f8a9b0"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE dossiestrategicostatus AS ENUM ('rascunho','aprovado','arquivado');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END 
        $$
    """)

    op.create_table(
        "dossies_estrategicos",
        sa.Column("id",             sa.String(36), primary_key=True),
        sa.Column("case_id",        sa.String(36),
                  sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("versao",         sa.Integer, nullable=False, server_default="1"),
        sa.Column("titulo",         sa.String(300)),
        sa.Column("conteudo_texto", sa.Text),
        sa.Column("conteudo_html",  sa.Text),
        sa.Column("secoes_json",    sa.Text),
        sa.Column("status",         PG_ENUM("rascunho","aprovado","arquivado",
                                            name="dossiestrategicostatus", create_type=False),
                  nullable=False, server_default="rascunho"),
        sa.Column("modelo_ia",      sa.String(100)),
        sa.Column("provedor_ia",    sa.String(30)),
        sa.Column("tokens_usados",  sa.Integer),
        sa.Column("gerado_por",     sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("aprovado_por",   sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("aprovado_em",    sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at",     sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at",     sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_dossie_case",   "dossies_estrategicos", ["case_id"])
    op.create_index("ix_dossie_status", "dossies_estrategicos", ["status"])


def downgrade() -> None:
    op.drop_table("dossies_estrategicos")
    op.execute("DROP TYPE IF EXISTS dossiestrategicostatus")
