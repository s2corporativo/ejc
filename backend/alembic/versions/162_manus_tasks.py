"""162 — tarefas assíncronas Manus API.

Tabela aditiva para rastrear o ciclo de vida de análises externas sem guardar
conteúdo bruto de resposta. O prompt persistido já chega sanitizado e o
resultado só é gravado após validação do structured output.
"""

from alembic import op
import sqlalchemy as sa

revision = "162_manus_tasks"
down_revision = "161_fee_estornos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "manus_tasks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("manus_task_id", sa.String(length=120), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", sa.String(length=36), sa.ForeignKey("cases.id", ondelete="SET NULL"), nullable=True),
        sa.Column("task_type", sa.String(length=50), nullable=False, server_default="case_intelligence"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="created"),
        sa.Column("stop_reason", sa.String(length=20), nullable=True),
        sa.Column("prompt_sanitizado", sa.Text(), nullable=False),
        sa.Column("resultado_json", sa.JSON(), nullable=True),
        sa.Column("mensagem_sanitizada", sa.Text(), nullable=True),
        sa.Column("erro_codigo", sa.String(length=80), nullable=True),
        sa.Column("erro_mensagem", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(length=120), nullable=True),
        sa.Column("ultimo_evento_id", sa.String(length=160), nullable=True),
        sa.Column("task_url", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("manus_task_id", name="uq_manus_tasks_manus_task_id"),
        sa.UniqueConstraint("ultimo_evento_id", name="uq_manus_tasks_ultimo_evento_id"),
    )
    op.create_index("ix_manus_tasks_user_id", "manus_tasks", ["user_id"])
    op.create_index("ix_manus_tasks_case_id", "manus_tasks", ["case_id"])
    op.create_index("ix_manus_tasks_status", "manus_tasks", ["status"])


def downgrade() -> None:
    op.drop_index("ix_manus_tasks_status", table_name="manus_tasks")
    op.drop_index("ix_manus_tasks_case_id", table_name="manus_tasks")
    op.drop_index("ix_manus_tasks_user_id", table_name="manus_tasks")
    op.drop_table("manus_tasks")
