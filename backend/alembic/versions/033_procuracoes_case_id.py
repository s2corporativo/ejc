"""procuracoes_case_id — vincula procurações a cases

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa

revision = 'e3f4a5b6c7d8'
down_revision = 'd2e3f4a5b6c7'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    existing = [row[0] for row in conn.execute(
        sa.text("SELECT column_name FROM information_schema.columns "
                "WHERE table_name='procuracoes' AND column_name='case_id'")
    )]
    if not existing:
        op.add_column(
            'procuracoes',
            sa.Column('case_id', sa.String,
                      sa.ForeignKey('cases.id', ondelete='SET NULL'), nullable=True)
        )
        op.create_index('ix_procuracoes_case_id', 'procuracoes', ['case_id'])


def downgrade():
    try:
        op.drop_index('ix_procuracoes_case_id', 'procuracoes')
        op.drop_column('procuracoes', 'case_id')
    except Exception:
        pass
