"""EJC v3.3 — Segurança: pwd_reset, must_change, bruteforce, device_alert

Revision ID: 004_seguranca
Revises: 003_expansao
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa

revision = "004_seguranca"
down_revision = "003_expansao"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Flag: troca obrigatória de senha no 1º login ──────────────────
    op.add_column("users", sa.Column(
        "must_change_password", sa.Boolean,
        server_default="false", nullable=False,
    ))

    # ── Tokens de recuperação de senha (one-time, expirável) ──────────
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36),
                  sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("used", sa.Boolean, server_default="false"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_solicitante", sa.String(45)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── IPs conhecidos por usuário (base para alerta de novo device) ──
    op.create_table(
        "user_known_ips",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36),
                  sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("ip", sa.String(45), nullable=False),
        sa.Column("user_agent_hash", sa.String(16)),
        sa.Column("primeira_vez_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "ip", name="uq_user_ip"),
    )


def downgrade() -> None:
    op.drop_table("user_known_ips")
    op.drop_table("password_reset_tokens")
    op.drop_column("users", "must_change_password")
