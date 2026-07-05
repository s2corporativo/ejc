"""070 — campo dedicado da crítica adversarial em ai_logs (Fase 5 / Modo Duas IAs)

A crítica adversarial deixava de viver concatenada em ai_logs.resposta e passa a
um campo PRÓPRIO. Motivo (auditoria Fase 5):
  • o gate de aprovação HITL varre `resposta` — a jurisprudência ESPECULATIVA da
    crítica ("verificar fonte") travava a aprovação sob CITACOES_POLITICA=bloquear;
  • a ingestão RAG de AI log aprovado destila `resposta` — a crítica especulativa
    contaminava a base de conhecimento.
Movendo a crítica para `critica_adversarial`, ambos os fluxos passam a ver só a
peça, sem enfraquecer nenhum controle.

ADITIVO PURO — nenhuma coluna existente é tocada. IDEMPOTENTE: ADD/DROP IF [NOT] EXISTS.

Revision ID: 070_ai_log_critica_adversarial
Revises: 069_api_keys
Create Date: 2026-07-05
"""
from alembic import op

revision = "070_ai_log_critica_adversarial"
down_revision = "069_api_keys"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE ai_logs ADD COLUMN IF NOT EXISTS critica_adversarial TEXT"
    )


def downgrade():
    op.execute("ALTER TABLE ai_logs DROP COLUMN IF EXISTS critica_adversarial")
