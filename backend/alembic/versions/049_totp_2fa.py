"""049 totp 2fa

Revision ID: 049_totp_2fa
Revises: 048
Create Date: 2026-06-25

Adiciona suporte a TOTP (autenticação de dois fatores) na tabela users.
"""
from alembic import op
import sqlalchemy as sa

revision = "049_totp_2fa"
down_revision = "048_processes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_secret", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("totp_enabled", sa.Boolean(), nullable=False,
                                     server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_secret")
