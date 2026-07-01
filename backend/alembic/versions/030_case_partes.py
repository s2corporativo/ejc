"""case_partes — partes processuais por caso

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa

revision = 'b0c1d2e3f4a5'
down_revision = 'a9b0c1d2e3f4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'case_partes',
        sa.Column('id', sa.String, primary_key=True,
                  server_default=sa.text("gen_random_uuid()::text")),
        sa.Column('case_id', sa.String,
                  sa.ForeignKey('cases.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tipo', sa.String(30), nullable=False),
        sa.Column('papel_processual', sa.String(100)),
        sa.Column('nome', sa.String(255), nullable=False),
        sa.Column('cpf_cnpj', sa.String(18)),
        sa.Column('qualificacao', sa.Text),
        sa.Column('email', sa.String(255)),
        sa.Column('telefone', sa.String(20)),
        sa.Column('representante_legal', sa.String(255)),
        sa.Column('oab', sa.String(20)),
        sa.Column('client_id', sa.String,
                  sa.ForeignKey('clients.id', ondelete='SET NULL'), nullable=True),
        sa.Column('ativo', sa.Boolean, server_default='true'),
        sa.Column('observacoes', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()')),
        sa.Column('created_by', sa.String),
    )
    op.create_index('ix_case_partes_case_id', 'case_partes', ['case_id'])
    op.create_index('ix_case_partes_tipo', 'case_partes', ['tipo'])


def downgrade():
    op.drop_table('case_partes')
