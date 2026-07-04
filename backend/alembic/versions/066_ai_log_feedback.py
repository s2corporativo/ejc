"""066 — feedback do usuário em ai_logs (feature #4)

Captura o 👍/👎 do usuário sobre a resposta da IA, para futura curadoria de
qualidade (HITL) e métricas. ADITIVO PURO — nenhuma coluna existente é tocada.

Colunas novas:
- feedback: avaliação do usuário. Valores esperados:
  'util' | 'nao_util' | NULL (sem feedback ainda). Mantido como VARCHAR (não
  enum) para evoluir sem ALTER TYPE — coerente com o baixo custo e a natureza
  livre desse rótulo.
- feedback_em: timestamp de quando o feedback foi registrado.

IDEMPOTENTE: ADD COLUMN IF NOT EXISTS.

Revision ID: 066_ai_log_feedback
Revises: 065_djen_prazo_assistido
Create Date: 2026-07-04
"""
from alembic import op

revision = "066_ai_log_feedback"
down_revision = "065_djen_prazo_assistido"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE ai_logs ADD COLUMN IF NOT EXISTS feedback VARCHAR(20)"
    )
    op.execute(
        "ALTER TABLE ai_logs ADD COLUMN IF NOT EXISTS "
        "feedback_em TIMESTAMPTZ"
    )


def downgrade():
    op.execute("ALTER TABLE ai_logs DROP COLUMN IF EXISTS feedback_em")
    op.execute("ALTER TABLE ai_logs DROP COLUMN IF EXISTS feedback")
