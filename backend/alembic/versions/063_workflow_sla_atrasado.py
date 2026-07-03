"""058 — workflow SLA: valor 'atrasado' no enum workflowstatus

Necessária porque as migrações 017/052 criaram o tipo `workflowstatus`
apenas com ('ativo','pausado','concluido','cancelado') — sem 'atrasado'.
O scheduler de SLA (app/services/scheduler.py::_verificar_sla_workflows)
marca CaseWorkflow.status='atrasado' quando a etapa atual estoura o
`sla_dias_uteis`; sem este valor no enum o UPDATE falharia no Postgres.

Nenhuma coluna nova: reusa colunas existentes (WorkflowHistorico.observacao
com marcadores '[alerta_sla]'/'[sla_vencido]' garante idempotência das
notificações). IDEMPOTENTE: ADD VALUE IF NOT EXISTS.

Revision ID: 058_workflow_sla_atrasado
Revises: 057_redesign_tables
Create Date: 2026-07-03
"""
from alembic import op

revision = "063_workflow_sla_atrasado"
down_revision = "062_redesign_tables"
branch_labels = None
depends_on = None


def upgrade():
    # ALTER TYPE ... ADD VALUE não pode rodar dentro da transação da migração
    # (restrição do Postgres) — autocommit_block resolve.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE workflowstatus ADD VALUE IF NOT EXISTS 'atrasado'")


def downgrade():
    # Postgres não suporta remover valor de enum sem recriar o tipo inteiro
    # (e reescrever a coluna). O valor extra é inócuo — no-op seguro.
    pass
