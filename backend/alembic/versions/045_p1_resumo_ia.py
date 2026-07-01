"""P1: resumo_ia em case_movimentos (tradução de andamentos por IA)

Aditivo e idempotente — usa ADD COLUMN IF NOT EXISTS porque o grafo do Alembic
no host foi reconstruído via stub 044 (migrations 040-044 aplicadas direto no
container). Seguro mesmo que a coluna já exista no volume pgdata.
"""
from alembic import op  # noqa
import sqlalchemy as sa  # noqa

revision = '045_p1_resumo_ia'
down_revision = '044'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE case_movimentos ADD COLUMN IF NOT EXISTS resumo_ia TEXT")


def downgrade():
    op.execute("ALTER TABLE case_movimentos DROP COLUMN IF EXISTS resumo_ia")
