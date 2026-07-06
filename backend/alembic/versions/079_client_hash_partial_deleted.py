"""079 — dedup de CPF/CNPJ (hash) exclui soft-deleted

Corrige o índice único parcial criado na migration 061: ux_clients_cpf_hash e
ux_clients_cnpj_hash filtravam apenas `<coluna> IS NOT NULL`, sem excluir
registros soft-deletados. Isso contradizia a migration 075, que substituiu os
únicos de cpf/cnpj por únicos PARCIAIS com `deleted_at IS NULL` justamente para
permitir RECADASTRAR o mesmo CPF/CNPJ após um soft-delete.

Como o dual-write popula cpf_hash/cnpj_hash na criação (clients.py) e o
soft-delete NÃO zera o hash (só a anonimização zera), um cliente soft-deletado
continuava ocupando o hash e o recadastro do mesmo CPF violava
ux_clients_cpf_hash — quebrando o comportamento que a 075 documenta como
suportado. Aqui recriamos os índices alinhando o predicado à 075.

Idempotente (DROP INDEX IF EXISTS + CREATE UNIQUE INDEX IF NOT EXISTS).

Revision ID: 079_client_hash_partial_deleted
Revises: 078_seed_kanban_columns
Create Date: 2026-07-06
"""
from alembic import op

revision = "079_client_hash_partial_deleted"
down_revision = "078_seed_kanban_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_clients_cpf_hash")
    op.execute("DROP INDEX IF EXISTS ux_clients_cnpj_hash")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_clients_cpf_hash "
        "ON clients (cpf_hash) WHERE cpf_hash IS NOT NULL AND deleted_at IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_clients_cnpj_hash "
        "ON clients (cnpj_hash) WHERE cnpj_hash IS NOT NULL AND deleted_at IS NULL"
    )


def downgrade() -> None:
    # Volta ao predicado da 061 (sem deleted_at).
    op.execute("DROP INDEX IF EXISTS ux_clients_cpf_hash")
    op.execute("DROP INDEX IF EXISTS ux_clients_cnpj_hash")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_clients_cpf_hash "
        "ON clients (cpf_hash) WHERE cpf_hash IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_clients_cnpj_hash "
        "ON clients (cnpj_hash) WHERE cnpj_hash IS NOT NULL"
    )
