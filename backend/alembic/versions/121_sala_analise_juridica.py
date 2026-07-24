"""Adiciona memória conversacional à análise preliminar.

Revision ID: 121_sala_analise_juridica
Revises: 120_chunk_pagina
Create Date: 2026-07-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "121_sala_analise_juridica"
down_revision = "120_chunk_pagina"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "raio_x_analises",
        sa.Column(
            "conversa",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "raio_x_analises",
        sa.Column(
            "estado_analise",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "raio_x_analises",
        sa.Column("ultima_consolidacao_em", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("raio_x_analises", "ultima_consolidacao_em")
    op.drop_column("raio_x_analises", "estado_analise")
    op.drop_column("raio_x_analises", "conversa")
