"""recover head 044 (bridge stub)

As migrations 040-044 foram aplicadas diretamente no container e perdidas do
host quando o container foi recriado. O schema correspondente já está presente
no banco persistente (volume pgdata). Este stub apenas reconecta o grafo do
Alembic 039 -> 044 para que 'alembic upgrade head' seja no-op e o backend suba.
"""
from alembic import op  # noqa
import sqlalchemy as sa  # noqa

revision = '044'
down_revision = '039_jurimetria'
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
