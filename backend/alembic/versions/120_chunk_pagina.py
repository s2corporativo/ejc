"""Adiciona coluna pagina a knowledge_chunks para rastreabilidade por pagina.

Revision ID: 120_chunk_pagina
Revises: 119_base_rag_enum
Create Date: 2026-07-24
"""
from alembic import op
import sqlalchemy as sa

revision = "120_chunk_pagina"
down_revision = "119_base_rag_enum"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_chunks",
        sa.Column("pagina", sa.Integer(), nullable=True),
    )
    # indice parcial para consultas por pagina (chunks com pagina nao-nula)
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_pagina "
        "ON knowledge_chunks (pagina) WHERE pagina IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_pagina", table_name="knowledge_chunks")
    op.drop_column("knowledge_chunks", "pagina")
