"""Coluna ``sigilo_reforcado`` em ``cases`` (Issue #1194).

Decisão do titular (18/08, por chat): o piso `LOCAL_COMPLETO` de sanitização
de IA (`app/services/ai/sanitization_policy.py`) foi reduzido a crimes
sexuais e menores/infância e juventude. O achado do `security-auditor` sobre
esse commit provou que a redução ficava **inalcançável** na prática: a área
autoritativa do caso (`Case.area`) só tem valores genéricos como `criminal` e
`familia` — nunca teve granularidade para "crime sexual" ou "menor" — e
nenhuma rota do sistema passa um `task_type`/`domain` de texto livre com essas
palavras. Um caso real de crime sexual contra menor, cadastrado hoje como
`area=criminal`, ia para o provedor externo pseudonimizado sem que nenhum
sinal do sistema soubesse que ele era sensível.

Esta migration abre o único caminho confiável: um campo explícito no caso,
setado pelo advogado na triagem (não inferido por palavra-chave), consultado
com prioridade máxima em `orchestrator.py`/`agent/loop.py` antes de resolver o
modo de sanitização pela área. Migration puramente aditiva: coluna boolean
`NOT NULL DEFAULT false`; nenhum caso existente muda de comportamento até
alguém marcar o campo.
"""

from alembic import op
import sqlalchemy as sa

revision = "146_case_sigilo_reforcado"
down_revision = "145_drop_orphan_db_only_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cases",
        sa.Column(
            "sigilo_reforcado",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    # Coluna sem dado derivado de outra tabela — perder a marcação é o único
    # efeito do rollback. Nenhuma outra tabela referencia a coluna.
    op.drop_column("cases", "sigilo_reforcado")
