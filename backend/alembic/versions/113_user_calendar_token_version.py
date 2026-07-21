"""113 — versão revogável da credencial pública do calendário ICS.

Revision ID: 113_user_calendar_token_version
Revises: 112_client_pii_drop_plaintext
Create Date: 2026-07-21
"""
from alembic import op
import sqlalchemy as sa


revision = "113_user_calendar_token_version"
down_revision = "112_client_pii_drop_plaintext"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "calendar_token_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "calendar_token_version")
