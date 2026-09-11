"""159 — CPF cifrado em perfis de usuários internos.

Revision ID: 159_user_cpf_secure
Revises: 158_case_partes_trabalhista_pii_expand

Adiciona somente storage cifrado (Fernet) e índice cego HMAC. Não existe
coluna plaintext de CPF em `users` e não há backfill automático.
"""
from alembic import op
import sqlalchemy as sa

revision = "159_user_cpf_secure"
down_revision = "158_case_partes_trabalhista_pii_expand"
branch_labels = None
depends_on = None
deployment_policy = "human_reviewed_unique_index"


def upgrade() -> None:
    op.add_column("users", sa.Column("cpf_enc", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("cpf_hash", sa.String(length=64), nullable=True))
    op.create_index(
        "ux_users_cpf_hash_active",
        "users",
        ["cpf_hash"],
        unique=True,
        postgresql_where=sa.text("cpf_hash IS NOT NULL AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    possui_cpf = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM users WHERE cpf_enc IS NOT NULL OR cpf_hash IS NOT NULL)")
    ).scalar()
    if possui_cpf:
        raise RuntimeError(
            "downgrade 159 bloqueado: existem CPFs cifrados; preserve os dados antes do rollback físico"
        )
    op.drop_index("ux_users_cpf_hash_active", table_name="users")
    op.drop_column("users", "cpf_hash")
    op.drop_column("users", "cpf_enc")
