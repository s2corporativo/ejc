"""portal_mensagens — chat cliente↔escritório por caso (FASE 8, Portal Corporativo)

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa

revision = 'a5b6c7d8e9f0'
down_revision = 'f4a5b6c7d8e9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'portal_mensagens',
        sa.Column('id', sa.String, primary_key=True,
                  server_default=sa.text("gen_random_uuid()::text")),
        sa.Column('case_id', sa.String,
                  sa.ForeignKey('cases.id', ondelete='CASCADE'), nullable=False),
        sa.Column('autor_tipo', sa.String(20), nullable=False),  # cliente | escritorio
        sa.Column('autor_id', sa.String,
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('autor_nome', sa.String(150)),
        sa.Column('mensagem', sa.Text, nullable=False),
        sa.Column('lida', sa.Boolean, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_portal_msg_case', 'portal_mensagens', ['case_id', 'created_at'])


def downgrade():
    op.drop_index('ix_portal_msg_case', table_name='portal_mensagens')
    op.drop_table('portal_mensagens')
