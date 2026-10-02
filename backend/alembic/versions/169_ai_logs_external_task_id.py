"""Correlação de AILog com tarefa assíncrona externa (Manus).

Aditiva e idempotente: ADD COLUMN / CREATE INDEX com IF NOT EXISTS, de modo
que reexecução (ou ambiente que já tenha a coluna) não falha.

Revision ID: 169_ai_logs_external_task_id
Revises: 168_finance_ged_links
Create Date: 2026-10-02
"""
from alembic import op

revision = "169_ai_logs_external_task_id"
down_revision = "168_finance_ged_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE ai_logs ADD COLUMN IF NOT EXISTS external_task_id VARCHAR(128)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ai_logs_external_task_id "
        "ON ai_logs (external_task_id)"
    )


def downgrade() -> None:
    # Remove somente o que esta revisão criou; nenhum dado de outras colunas é
    # tocado. O conteúdo de external_task_id é derivável de fontes_rag
    # ("[manus_task] <id>"), que permanece por compatibilidade.
    op.execute("DROP INDEX IF EXISTS ix_ai_logs_external_task_id")
    op.execute("ALTER TABLE ai_logs DROP COLUMN IF EXISTS external_task_id")
