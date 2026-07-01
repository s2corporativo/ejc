"""Biblioteca de Prompts Jurídicos — tabela prompts_juridicos

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE promptcategoria AS ENUM (
                    'peticao','contrato','audiencia','email',
                    'modelo','analise','resumo','negociacao','outros'
                );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END 
        $$
    """)

    op.create_table(
        "prompts_juridicos",
        sa.Column("id",               sa.String(36),  primary_key=True),
        sa.Column("titulo",           sa.String(200), nullable=False),
        sa.Column("categoria",        PG_ENUM(
            "peticao","contrato","audiencia","email",
            "modelo","analise","resumo","negociacao","outros",
            name="promptcategoria", create_type=False), nullable=False),
        sa.Column("conteudo",         sa.Text, nullable=False),
        sa.Column("descricao",        sa.Text),
        sa.Column("variaveis",        sa.Text),
        sa.Column("tags",             sa.Text),
        sa.Column("favorito",         sa.Boolean, nullable=False, server_default="false"),
        sa.Column("publico",          sa.Boolean, nullable=False, server_default="true"),
        sa.Column("vezes_executado",  sa.Integer, nullable=False, server_default="0"),
        sa.Column("ultima_execucao",  sa.DateTime(timezone=True)),
        sa.Column("avaliacao_media",  sa.Float),
        sa.Column("versao",           sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_by",       sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at",       sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at",       sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at",       sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_prompts_juridicos_categoria", "prompts_juridicos", ["categoria"])
    op.create_index("ix_prompts_juridicos_favorito",  "prompts_juridicos", ["favorito"])
    op.create_index("ix_prompts_juridicos_deleted_at","prompts_juridicos", ["deleted_at"])


def downgrade() -> None:
    op.drop_table("prompts_juridicos")
    op.execute("DROP TYPE IF EXISTS promptcategoria")
