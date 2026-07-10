"""080 — preferências de notificações por usuário

Cria uma tabela isolada, sem alterar notificações históricas, para armazenar
preferências de canais externos e categorias opcionais. Alertas internos críticos
continuam obrigatórios na camada de serviço.

Revision ID: 080_notification_preferences
Revises: 079_client_hash_partial_deleted
Create Date: 2026-07-10
"""

from alembic import op
import sqlalchemy as sa

revision = "080_notification_preferences"
down_revision = "079_client_hash_partial_deleted"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_preferences",
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("push_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("whatsapp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("prazos_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("tarefas_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("intimacoes_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("audiencias_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("documentos_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("assinaturas_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("financeiro_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("diario_oficial_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("resumo_diario", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("quiet_hours_start", sa.Time(), nullable=True),
        sa.Column("quiet_hours_end", sa.Time(), nullable=True),
        sa.Column(
            "timezone",
            sa.String(length=64),
            nullable=False,
            server_default="America/Sao_Paulo",
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
            "(quiet_hours_start IS NULL AND quiet_hours_end IS NULL) OR "
            "(quiet_hours_start IS NOT NULL AND quiet_hours_end IS NOT NULL)",
            name="ck_notification_preferences_quiet_hours_pair",
        ),
    )


def downgrade() -> None:
    op.drop_table("notification_preferences")
