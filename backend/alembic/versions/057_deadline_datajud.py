"""057_deadline_datajud — BUG-16: origem + referencia_datajud em deadlines

Adiciona rastreabilidade de prazos importados do DataJud:
- origem: 'manual' (default) | 'datajud'
- referencia_datajud: chave de dedup do movimento (hash CNJ|data|titulo)

Idempotente (ADD COLUMN IF NOT EXISTS / CREATE INDEX IF NOT EXISTS) para
suportar deploy limpo e produção onde a coluna possa já existir.

Revision ID: 057_deadline_datajud
Revises: 056_processes_is_principal
"""
from alembic import op

revision = "057_deadline_datajud"
down_revision = "056_processes_is_principal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE deadlines "
        "ADD COLUMN IF NOT EXISTS origem varchar(20) NOT NULL DEFAULT 'manual'"
    )
    op.execute(
        "ALTER TABLE deadlines "
        "ADD COLUMN IF NOT EXISTS referencia_datajud varchar(64)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_deadlines_referencia_datajud "
        "ON deadlines(referencia_datajud)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_deadlines_referencia_datajud")
    op.execute("ALTER TABLE deadlines DROP COLUMN IF EXISTS referencia_datajud")
    op.execute("ALTER TABLE deadlines DROP COLUMN IF EXISTS origem")
