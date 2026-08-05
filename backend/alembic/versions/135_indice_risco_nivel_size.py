"""Expandir coluna risco_nivel de VARCHAR(10) para VARCHAR(15).

A classificação "indeterminado" possui 13 caracteres e não cabe em VARCHAR(10).
O /recalcular falha com 'value too long for type character varying(10)' e retorna 500.

Revision ID: 135_indice_risco_nivel_size
Revises: 134_processes_numero_cnj_index
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa

revision = "135_indice_risco_nivel_size"
down_revision = "132_case_parte_pii_encriptado"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("cases", "risco_nivel", type_=sa.String(15), existing_type=sa.String(10))
    op.alter_column("indice_risco_historico", "nivel", type_=sa.String(15), existing_type=sa.String(10))


def downgrade() -> None:
    from sqlalchemy import text
    conn = op.get_bind()

    # Pré-verificação: detectar valores que não cabem em VARCHAR(10)
    historico_valores = conn.execute(
        text("SELECT COUNT(*) FROM indice_risco_historico WHERE LENGTH(nivel) > 10")
    ).scalar() or 0

    cases_valores = conn.execute(
        text("SELECT COUNT(*) FROM cases WHERE LENGTH(risco_nivel) > 10")
    ).scalar() or 0

    if historico_valores > 0 or cases_valores > 0:
        raise RuntimeError(
            f"Reversão bloqueada: indice_risco_historico={historico_valores} valores, "
            f"cases={cases_valores} valores com >10 caracteres. "
            "Preserve os dados sem truncamento; migração reversa exige aprovação."
        )

    op.alter_column("indice_risco_historico", "nivel", type_=sa.String(10), existing_type=sa.String(15))
    op.alter_column("cases", "risco_nivel", type_=sa.String(10), existing_type=sa.String(15))
