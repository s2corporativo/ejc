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
    # Idempotente (IF NOT EXISTS): o baseline 048_processes já cria `users` com
    # estas colunas via create_all (o modelo User as possui). Mantida na cadeia
    # por fidelidade histórica; em banco já existente vira no-op.
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_secret VARCHAR(64)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_enabled BOOLEAN NOT NULL DEFAULT FALSE")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS totp_enabled")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS totp_secret")
