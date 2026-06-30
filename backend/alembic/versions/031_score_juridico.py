"""score_juridico — avaliação multidimensional de peças

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'c1d2e3f4a5b6'
down_revision = 'b0c1d2e3f4a5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'score_juridico',
        sa.Column('id', sa.String, primary_key=True,
                  server_default=sa.text("gen_random_uuid()::text")),
        sa.Column('case_id', sa.String,
                  sa.ForeignKey('cases.id', ondelete='CASCADE'), nullable=False),
        sa.Column('avaliador_id', sa.String, nullable=True),
        sa.Column('tipo', sa.String(20), server_default='ia'),

        # 7 dimensões (total 100 pts)
        sa.Column('pedido', sa.Integer, server_default='0'),               # 0-15
        sa.Column('causa_de_pedir', sa.Integer, server_default='0'),       # 0-15
        sa.Column('fundamentacao', sa.Integer, server_default='0'),        # 0-20
        sa.Column('provas', sa.Integer, server_default='0'),               # 0-20
        sa.Column('jurisprudencia', sa.Integer, server_default='0'),       # 0-15
        sa.Column('documentos_obrigatorios', sa.Integer, server_default='0'),  # 0-10
        sa.Column('conformidade_formal', sa.Integer, server_default='0'), # 0-5
        sa.Column('total', sa.Integer, server_default='0'),

        sa.Column('detalhes', JSONB),
        sa.Column('recomendacoes', JSONB),
        sa.Column('versao', sa.Integer, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()')),
    )
    op.create_index('ix_score_juridico_case_id', 'score_juridico', ['case_id'])
    op.create_index('ix_score_juridico_created',
                    'score_juridico', ['case_id', 'created_at'])


def downgrade():
    op.drop_table('score_juridico')
