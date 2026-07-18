"""098 — deadlines.concluido_por: registra QUEM deu baixa no prazo (auditoria)

Contexto:
    A baixa (conclusão) de um prazo grava apenas `data_conclusao`, sem registrar
    QUEM concluiu — lacuna de auditoria. Adiciona `concluido_por`
    (VARCHAR(36), nullable), espelhando a coluna audit-actor
    `ciencia_confirmada_por` da própria tabela deadlines (String(36), SEM FK):
    guarda o id do usuário que realizou a ação sem impor RESTRICT na exclusão de
    usuários e sem acoplar a integridade de dados de auditoria ao ciclo de vida
    da conta.

    A LÓGICA de preenchimento é responsabilidade do backend
    (routers/deadlines.py) — fora do escopo desta migration, que só ajusta o
    schema.

Idempotente (IF NOT EXISTS), seguindo o padrão raw-SQL das migrations de
deadlines (057_deadline_datajud / 077_deadline_confirmado_doc).

Revision ID: 098_deadline_concluido_por
Revises: 097_fee_tipo_sucumbencia
"""
from alembic import op

revision = "098_deadline_concluido_por"
down_revision = "097_fee_tipo_sucumbencia"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE deadlines "
        "ADD COLUMN IF NOT EXISTS concluido_por varchar(36)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE deadlines DROP COLUMN IF EXISTS concluido_por")
