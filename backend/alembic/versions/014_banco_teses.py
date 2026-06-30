"""Banco de Teses Jurídicas — tabelas teses e tese_caso_links

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Criar ENUMs primeiro — idempotente via EXCEPTION
    bind = op.get_bind()
    bind.execute(sa.text("""
        DO $$ BEGIN
            CREATE TYPE tesetipo AS ENUM (
                'escritorio','sugerida_ia','doutrina','jurisprudencia','externa'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """))
    bind.execute(sa.text("""
        DO $$ BEGIN
            CREATE TYPE tesestatus AS ENUM ('rascunho','ativa','arquivada');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """))

    # Usar PG_ENUM(create_type=False) para que op.create_table NÃO tente recriar
    tipo_col   = PG_ENUM("escritorio","sugerida_ia","doutrina","jurisprudencia","externa",
                         name="tesetipo",  create_type=False)
    status_col = PG_ENUM("rascunho","ativa","arquivada",
                         name="tesestatus", create_type=False)

    op.create_table(
        "teses",
        sa.Column("id",               sa.String(36),  primary_key=True),
        sa.Column("titulo",           sa.String(300), nullable=False),
        sa.Column("descricao",        sa.Text,        nullable=False),
        sa.Column("fundamentacao",    sa.Text),
        sa.Column("jurisprudencia",   sa.Text),
        sa.Column("contra_argumento", sa.Text),
        sa.Column("area_juridica",    sa.String(60)),
        sa.Column("tribunal",         sa.String(120)),
        sa.Column("magistrado",       sa.String(200)),
        sa.Column("tags",             sa.Text),
        sa.Column("observacoes",      sa.Text),
        sa.Column("tipo",   tipo_col,   nullable=False, server_default="escritorio"),
        sa.Column("status", status_col, nullable=False, server_default="ativa"),
        sa.Column("vezes_usada",   sa.Integer, nullable=False, server_default="0"),
        sa.Column("vezes_venceu",  sa.Integer, nullable=False, server_default="0"),
        sa.Column("vezes_perdeu",  sa.Integer, nullable=False, server_default="0"),
        sa.Column("taxa_sucesso",  sa.Float),
        sa.Column("created_by",    sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_teses_area_juridica", "teses", ["area_juridica"])
    op.create_index("ix_teses_status",        "teses", ["status"])
    op.create_index("ix_teses_deleted_at",    "teses", ["deleted_at"])

    op.create_table(
        "tese_caso_links",
        sa.Column("id",         sa.String(36), primary_key=True),
        sa.Column("tese_id",    sa.String(36),
                  sa.ForeignKey("teses.id",  ondelete="CASCADE"), nullable=False),
        sa.Column("case_id",    sa.String(36),
                  sa.ForeignKey("cases.id",  ondelete="CASCADE"), nullable=False),
        sa.Column("resultado",  sa.String(20)),
        sa.Column("observacao", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by", sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_tese_caso_links_tese", "tese_caso_links", ["tese_id"])
    op.create_index("ix_tese_caso_links_case", "tese_caso_links", ["case_id"])


def downgrade() -> None:
    op.drop_table("tese_caso_links")
    op.drop_table("teses")
    op.execute("DROP TYPE IF EXISTS tesetipo")
    op.execute("DROP TYPE IF EXISTS tesestatus")
