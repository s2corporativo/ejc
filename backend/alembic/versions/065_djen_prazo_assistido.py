"""065 — prazo assistido em djen_comunicacoes (feature #1)

Fluxo "prazo assistido": a partir do texto da intimação o sistema SUGERE um
prazo (heurística por tipo) e o advogado ACEITA/RECUSA. Precisamos rastrear
esse estado por comunicação e, quando aceito, vincular o Deadline criado.

Colunas novas (ADITIVO PURO — nenhuma coluna existente é tocada):
- prazo_sugerido_status: rastreia o estado do fluxo. Valores esperados:
  'nenhum' (default lógico) | 'sugerido' | 'aceito' | 'recusado'.
  Nullable com default 'nenhum' — comunicações antigas ficam consistentes.
- prazo_deadline_id: id do Deadline (deadlines.id, String(36) UUID) criado
  quando o prazo é aceito. FK LÓGICA (sem constraint física), seguindo o
  padrão de várias colunas de referência do projeto — ex.:
  DjenComunicacao.processada_por e AILog.revisado_por são String(36) sem FK.
  Evita acoplar o ciclo de vida da intimação ao do Deadline (um Deadline
  removido não deve travar/cascatear na comunicação).

IDEMPOTENTE: ADD COLUMN IF NOT EXISTS.

Revision ID: 065_djen_prazo_assistido
Revises: 064_drive_columns
Create Date: 2026-07-04
"""
from alembic import op

revision = "065_djen_prazo_assistido"
down_revision = "064_drive_columns"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE djen_comunicacoes ADD COLUMN IF NOT EXISTS "
        "prazo_sugerido_status VARCHAR(20) DEFAULT 'nenhum'"
    )
    op.execute(
        "ALTER TABLE djen_comunicacoes ADD COLUMN IF NOT EXISTS "
        "prazo_deadline_id VARCHAR(36)"
    )


def downgrade():
    op.execute(
        "ALTER TABLE djen_comunicacoes DROP COLUMN IF EXISTS prazo_deadline_id"
    )
    op.execute(
        "ALTER TABLE djen_comunicacoes DROP COLUMN IF EXISTS prazo_sugerido_status"
    )
