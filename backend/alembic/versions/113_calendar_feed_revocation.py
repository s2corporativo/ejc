"""113 — credencial versionada e revogável do feed ICS.

Revision ID: 113_calendar_feed_revocation
Revises: 112_client_pii_drop_plaintext
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa


revision = "113_calendar_feed_revocation"
down_revision = "112_client_pii_drop_plaintext"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendar_feed_credentials",
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("calendar_feed_credentials")
