"""160 — estado persistente dos alertas inteligentes do Dashboard.

Tabela aditiva e polimórfica para reconhecimento por usuário. Não altera o
status de deadlines/tasks/intimações/movimentações e não cria dependência entre
entidades jurídicas distintas.

Revision ID: 160_activity_alert_states
Revises: 159_user_cpf_secure
"""
from alembic import op
import sqlalchemy as sa

revision = "160_activity_alert_states"
down_revision = "159_user_cpf_secure"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "activity_alert_states",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("visualizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tratado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "user_id", "source_type", "source_id", name="uq_activity_alert_user_source"
        ),
    )
    op.create_index("ix_activity_alert_states_user_id", "activity_alert_states", ["user_id"])
    op.create_index("ix_activity_alert_states_source_type", "activity_alert_states", ["source_type"])
    op.create_index("ix_activity_alert_states_source_id", "activity_alert_states", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_activity_alert_states_source_id", table_name="activity_alert_states")
    op.drop_index("ix_activity_alert_states_source_type", table_name="activity_alert_states")
    op.drop_index("ix_activity_alert_states_user_id", table_name="activity_alert_states")
    op.drop_table("activity_alert_states")
