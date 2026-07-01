"""038_fix_missing_columns — adiciona colunas faltantes em knowledge_chunks, teses e checklist_templates

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa

revision = 'd8e9f0a1b2c3'
down_revision = 'c7d8e9f0a1b2'
branch_labels = None
depends_on = None


def upgrade():
    # knowledge_chunks.categoria (usado no RAG — buscar_contexto_rag)
    with op.batch_alter_table('knowledge_chunks') as batch_op:
        batch_op.add_column(
            sa.Column('categoria', sa.String(100), nullable=True),
            insert_before=None,
        )

    # teses.area_direito (filtro na listagem de teses)
    with op.batch_alter_table('teses') as batch_op:
        batch_op.add_column(
            sa.Column('area_direito', sa.String(100), nullable=True),
        )

    # checklist_templates.tipo_demanda (filtro por tipo de demanda)
    with op.batch_alter_table('checklist_templates') as batch_op:
        batch_op.add_column(
            sa.Column('tipo_demanda', sa.String(100), nullable=True),
        )


def downgrade():
    with op.batch_alter_table('knowledge_chunks') as batch_op:
        batch_op.drop_column('categoria')

    with op.batch_alter_table('teses') as batch_op:
        batch_op.drop_column('area_direito')

    with op.batch_alter_table('checklist_templates') as batch_op:
        batch_op.drop_column('tipo_demanda')
