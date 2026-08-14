"""Índice em processes.numero_cnj — busca e ORDER BY sem varredura sequencial (DADOS-003, parcial).

Por que esta migration existe
──────────────────────────────
`processes.numero_cnj` não tinha índice algum: toda busca por número CNJ
(`search.py`, `processo_service.py`) varria a tabela inteira. Cresce junto
com o volume de processos do escritório — é exatamente o tipo de índice
ausente que só dói depois que a base cresce, não no dia em que a coluna foi
criada.

Por que NÃO é UNIQUE
─────────────────────
A auditoria (DADOS-003) também aponta a ausência de uma constraint UNIQUE,
que impediria processo duplicado entrar sem barreira estrutural. Essa parte
foi DELIBERADAMENTE deixada de fora: `ADD CONSTRAINT UNIQUE` numa tabela de
produção com dado real aborta a migration (e o deploy) se já existir
QUALQUER duplicata — e não há como saber se existe sem consultar o banco de
produção, o que este ambiente não tem acesso para fazer (regra 9 do
CLAUDE.md). Antes de tentar UNIQUE, rode em produção:

    SELECT numero_cnj, count(*) FROM processes
    WHERE numero_cnj IS NOT NULL GROUP BY numero_cnj HAVING count(*) > 1;

Zero linhas → seguro adicionar UNIQUE numa migration separada. Alguma linha →
decisão humana sobre qual registro é o canônico antes de poder constranger.

Revision ID: 134_processes_numero_cnj_index
Revises: 133_user_password_changed_at
Create Date: 2026-08-03

Renumerada de 129 para 134 em 2026-08-05 após PR #652 ser renumerada de 131
para 132. O down_revision foi repontado para 133_user_password_changed_at.
O DDL não mudou.
"""
from alembic import op

revision = "134_processes_numero_cnj_index"
down_revision = "133_user_password_changed_at"
branch_labels = None
depends_on = None

_INDICE = "ix_processes_numero_cnj"


def upgrade() -> None:
    op.create_index(_INDICE, "processes", ["numero_cnj"], unique=False, if_not_exists=True)


def downgrade() -> None:
    op.drop_index(_INDICE, table_name="processes", if_exists=True)
