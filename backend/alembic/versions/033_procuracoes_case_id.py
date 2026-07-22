"""procuracoes_case_id — vincula procurações a cases

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-06-17
"""

from alembic import op
import sqlalchemy as sa

revision = "e3f4a5b6c7d8"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    existing = [
        row[0]
        for row in conn.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='procuracoes' AND column_name='case_id'"
            )
        )
    ]
    if not existing:
        op.add_column(
            "procuracoes",
            sa.Column("case_id", sa.String, sa.ForeignKey("cases.id", ondelete="SET NULL"), nullable=True),
        )
        op.create_index("ix_procuracoes_case_id", "procuracoes", ["case_id"])


def downgrade():
    # DDL idempotente (IF EXISTS) em vez de try/except: pass.
    # O downgrade do EJC roda em UMA única transação (alembic/env.py). Ao cruzar
    # 036→033, a 036.downgrade() recria procuracoes.case_id SEM o índice
    # ix_procuracoes_case_id; o antigo op.drop_index falhava, ABORTAVA a transação
    # e o `except: pass` só mascarava — a migration 032 seguinte então quebrava com
    # InFailedSqlTransaction. Com IF EXISTS o rollback profundo nunca trava.
    # NOTA (regra do repo): só o downgrade() muda; o upgrade() já aplicado em
    # produção fica INTOCADO — a alteração afeta apenas reversões futuras.
    # (O DROP COLUMN já removeria a FK/índice; o DROP INDEX explícito é defensivo.)
    op.execute("DROP INDEX IF EXISTS ix_procuracoes_case_id")
    op.execute("ALTER TABLE procuracoes DROP COLUMN IF EXISTS case_id")
