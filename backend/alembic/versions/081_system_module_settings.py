"""081 — lifecycle e feature flags de módulos

Cria overrides administrativos para habilitação, visibilidade e substituição de
rotas. A tabela não concede autorização e não substitui RBAC.

Revision ID: 081_system_module_settings
Revises: 080_notification_preferences
Create Date: 2026-07-10
"""

from alembic import op
import sqlalchemy as sa

revision = "081_system_module_settings"
down_revision = "080_notification_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_module_settings",
        sa.Column("module_key", sa.String(length=100), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "menu_visible", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="active"
        ),
        sa.Column("replacement_route", sa.String(length=255), nullable=True),
        sa.Column("removal_date", sa.Date(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "updated_by",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'beta', 'hidden', 'legacy', 'disabled')",
            name="ck_system_module_settings_status",
        ),
        sa.CheckConstraint(
            "replacement_route IS NULL OR replacement_route LIKE '/%'",
            name="ck_system_module_settings_replacement_route",
        ),
    )


def downgrade() -> None:
    op.drop_table("system_module_settings")
