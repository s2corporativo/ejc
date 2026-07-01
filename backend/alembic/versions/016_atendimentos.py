"""Histórico de Atendimentos ao Cliente — tabela atendimentos

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE atendimentotipo AS ENUM (
                    'reuniao_presencial','reuniao_virtual','ligacao',
                    'email','whatsapp','protocolo','visita','outros'
                );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END 
        $$
    """)

    op.create_table(
        "atendimentos",
        sa.Column("id",                   sa.String(36), primary_key=True),
        sa.Column("client_id",            sa.String(36),
                  sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id",              sa.String(36),
                  sa.ForeignKey("cases.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tipo",                 PG_ENUM(
            "reuniao_presencial","reuniao_virtual","ligacao",
            "email","whatsapp","protocolo","visita","outros",
            name="atendimentotipo", create_type=False), nullable=False),
        sa.Column("data_atendimento",     sa.DateTime(timezone=True), nullable=False),
        sa.Column("duracao_min",          sa.String(10)),
        sa.Column("resumo",               sa.Text, nullable=False),
        sa.Column("proximo_passo",        sa.Text),
        sa.Column("observacoes_privadas", sa.Text),
        sa.Column("created_by",           sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at",           sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at",           sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_atendimentos_client",  "atendimentos", ["client_id"])
    op.create_index("ix_atendimentos_case",    "atendimentos", ["case_id"])
    op.create_index("ix_atendimentos_data",    "atendimentos", ["data_atendimento"])


def downgrade() -> None:
    op.drop_table("atendimentos")
    op.execute("DROP TYPE IF EXISTS atendimentotipo")
