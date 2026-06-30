"""Repositório de Jurisprudência Interna

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE juriresultado AS ENUM ('favoravel','desfavoravel','neutro','acordo');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END 
        $$
    """)

    op.create_table(
        "jurisprudencias_internas",
        sa.Column("id",               sa.String(36),  primary_key=True),
        sa.Column("titulo",           sa.String(300), nullable=False),
        sa.Column("ementa",           sa.Text, nullable=False),
        sa.Column("fundamentacao",    sa.Text),
        sa.Column("tribunal",         sa.String(120)),
        sa.Column("relator",          sa.String(200)),
        sa.Column("numero_acordao",   sa.String(100)),
        sa.Column("data_julgamento",  sa.Date),
        sa.Column("fonte",            sa.String(50)),
        sa.Column("link_original",    sa.Text),
        sa.Column("area_juridica",    sa.String(60)),
        sa.Column("tags",             sa.Text),
        sa.Column("resultado",        PG_ENUM("favoravel","desfavoravel","neutro","acordo",
                                              name="juriresultado", create_type=False), nullable=True),
        sa.Column("favorito",         sa.Boolean, nullable=False, server_default="false"),
        sa.Column("vezes_citada",     sa.Integer, nullable=False, server_default="0"),
        sa.Column("classificacao_ia", sa.Text),
        sa.Column("created_by",       sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at",       sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at",       sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at",       sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_juris_area",    "jurisprudencias_internas", ["area_juridica"])
    op.create_index("ix_juris_tribunal","jurisprudencias_internas", ["tribunal"])
    op.create_index("ix_juris_deleted", "jurisprudencias_internas", ["deleted_at"])


def downgrade() -> None:
    op.drop_table("jurisprudencias_internas")
    op.execute("DROP TYPE IF EXISTS juriresultado")
