"""Índices de apoio à reconciliação/unicidade lógica de CNJ.

Revision ID: 163_cnj_normalized_indexes
Revises: 162_case_financial_classification
Create Date: 2026-09-25

A unicidade é imposta pelos serviços canônicos com advisory lock global e
checagem cruzada cases/processes. Os índices NÃO são UNIQUE de propósito:
o módulo de saneamento precisa conseguir representar duplicidades legadas para
detectá-las e fundi-las de forma auditável.
"""
from alembic import op

revision = "163_cnj_normalized_indexes"
down_revision = "162_case_financial_classification"
branch_labels = None
depends_on = None

_CASE_INDEX = "ix_cases_cnj_normalized_active"
_PROCESS_INDEX = "ix_processes_cnj_normalized_active"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS {_CASE_INDEX}
        ON cases ((regexp_replace(numero_processo, '[^0-9]', '', 'g')))
        WHERE deleted_at IS NULL
          AND numero_processo IS NOT NULL
          AND length(regexp_replace(numero_processo, '[^0-9]', '', 'g')) = 20
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS {_PROCESS_INDEX}
        ON processes ((regexp_replace(numero_cnj, '[^0-9]', '', 'g')))
        WHERE deleted_at IS NULL
          AND numero_cnj IS NOT NULL
          AND length(regexp_replace(numero_cnj, '[^0-9]', '', 'g')) = 20
        """
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_PROCESS_INDEX}")
    op.execute(f"DROP INDEX IF EXISTS {_CASE_INDEX}")
