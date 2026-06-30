"""etiquetas — sistema de etiquetas/labels reutilizáveis aplicáveis a casos

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa

revision = 'c7d8e9f0a1b2'
down_revision = 'b6c7d8e9f0a1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'etiquetas',
        sa.Column('id', sa.String, primary_key=True,
                  server_default=sa.text("gen_random_uuid()::text")),
        sa.Column('nome', sa.String(60), nullable=False),
        sa.Column('cor', sa.String(20), server_default='#AA8660'),
        sa.Column('tipo', sa.String(20)),   # area | responsavel | fase | livre
        sa.Column('created_by', sa.String, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_table(
        'case_etiquetas',
        sa.Column('id', sa.String, primary_key=True,
                  server_default=sa.text("gen_random_uuid()::text")),
        sa.Column('case_id', sa.String,
                  sa.ForeignKey('cases.id', ondelete='CASCADE'), nullable=False),
        sa.Column('etiqueta_id', sa.String,
                  sa.ForeignKey('etiquetas.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_case_etiq_case', 'case_etiquetas', ['case_id'])
    op.create_unique_constraint('uq_case_etiqueta', 'case_etiquetas', ['case_id', 'etiqueta_id'])


def downgrade():
    op.drop_constraint('uq_case_etiqueta', 'case_etiquetas', type_='unique')
    op.drop_index('ix_case_etiq_case', table_name='case_etiquetas')
    op.drop_table('case_etiquetas')
    op.drop_table('etiquetas')
