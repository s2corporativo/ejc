"""159 — CPF cifrado em perfis de usuários internos.

Revision ID: 159_user_cpf_secure
Revises: 158_case_partes_trabalhista_pii_expand

Adiciona somente storage cifrado (Fernet) e índice cego HMAC. Não existe
coluna plaintext de CPF em `users` e não há backfill automático.
"""
from alembic import op

revision = "159_user_cpf_secure"
down_revision = "158_case_partes_trabalhista_pii_expand"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS cpf_enc text")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS cpf_hash varchar(64)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_users_cpf_hash_active "
        "ON users (cpf_hash) WHERE cpf_hash IS NOT NULL AND deleted_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_users_cpf_hash_active")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS cpf_hash")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS cpf_enc")
