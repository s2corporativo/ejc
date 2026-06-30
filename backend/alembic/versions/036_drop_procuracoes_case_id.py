"""drop procuracoes.case_id — coluna órfã (migration 033 adicionou, model nunca usou)

Procuração é vinculada ao CLIENTE (client_id), não ao caso. A coluna case_id
nunca foi mapeada no model nem preenchida (0 linhas). Removida na limpeza FASE 8.

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-06-17
"""
from alembic import op

revision = 'b6c7d8e9f0a1'
down_revision = 'a5b6c7d8e9f0'
branch_labels = None
depends_on = None


def upgrade():
    # DROP COLUMN remove automaticamente a FK/índice associados (Postgres)
    op.execute("ALTER TABLE procuracoes DROP COLUMN IF EXISTS case_id")


def downgrade():
    op.execute("ALTER TABLE procuracoes ADD COLUMN case_id VARCHAR REFERENCES cases(id)")
