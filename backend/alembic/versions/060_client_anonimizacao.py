"""060_client_anonimizacao: campo para direito ao esquecimento (LGPD art. 17)

ADITIVO: só ADD COLUMN, sem alterar/remover nada existente. Marca QUANDO um
cliente foi anonimizado (não SE é possível excluir fisicamente — dados de
clientes com casos/financeiro vinculados são preservados por obrigação legal/
fiscal, art. 16 II da LGPD; a anonimização de PII é o mecanismo real usado,
ver services/client_anonimizacao.py).

Revision ID: 060_client_anonimizacao
Revises: 059_archiving_cases_processes
"""
from alembic import op

revision = "060_client_anonimizacao"
down_revision = "059_archiving_cases_processes"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS anonimizado_em timestamptz")
    op.execute("CREATE INDEX IF NOT EXISTS ix_clients_anonimizado_em ON clients (anonimizado_em)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_clients_anonimizado_em")
    op.execute("ALTER TABLE clients DROP COLUMN IF EXISTS anonimizado_em")
