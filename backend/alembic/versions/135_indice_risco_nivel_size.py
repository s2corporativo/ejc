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
down_revision = "134_processes_numero_cnj_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("cases", "risco_nivel", type_=sa.String(15), existing_type=sa.String(10))
    op.alter_column("indice_risco_historico", "nivel", type_=sa.String(15), existing_type=sa.String(10))


def downgrade() -> None:
    # Sem pré-verificação dinâmica (porta do gate de deploy): o PostgreSQL
    # recusa nativamente a redução VARCHAR(15)→VARCHAR(10) quando existir
    # valor com mais de 10 caracteres ("value too long for type character
    # varying(10)") — o mesmo erro 500 que a migration de upgrade corrige.
    # Reversão com dados novos é bloqueada por CONSTRUÇÃO; preserve os dados
    # sem truncamento e trate como operação excepcional aprovada.
    op.alter_column("indice_risco_historico", "nivel", type_=sa.String(10), existing_type=sa.String(15))
    op.alter_column("cases", "risco_nivel", type_=sa.String(10), existing_type=sa.String(15))
