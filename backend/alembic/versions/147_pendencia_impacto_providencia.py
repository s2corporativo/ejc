"""Colunas ``impacto`` e ``providencia`` em ``client_pending_items`` (Issue #1244).

`docs/estrategia/EVOLUCAO_ESTRATEGICA_EJC.md`, frente 12 ("o que está
faltando?"): a lista de pendências do cliente já registra o QUE falta
(`type`, `title`, `due_date`) e em que estágio está (`status`), mas não diz
**quanto pesa** nem **como resolver**. Sem esses dois campos a tela é um
inventário: o advogado lê dez pendências, não sabe qual ataca primeiro e
precisa decidir caso a caso onde cada documento é obtido.

`impacto` responde a primeira pergunta (alto/médio/baixo) e `providencia` a
segunda — solicitar ao cliente, obter no processo, emitir certidão,
diligência externa, ou outro caminho. São exatamente as duas colunas que
convertem a lista em plano de ação.

Migration puramente aditiva e NULLABLE: as pendências que já existem ficam
com `NULL` nas duas colunas, o que a interface lê como "não informado" e
segue exibindo normalmente. Nenhum backfill, nenhuma mudança de
comportamento até alguém preencher o campo. O vocabulário é fechado no
schema Pydantic (`app/routers/pending_items.py`), não em CHECK constraint,
seguindo o padrão já usado por `type` e `status` nesta mesma tabela.
"""

from alembic import op
import sqlalchemy as sa

revision = "147_pendencia_impacto_providencia"
down_revision = "146_case_sigilo_reforcado"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # add_column com IF NOT EXISTS não existe no Alembic; a tabela é criada em
    # 053_reconcile_schema (SQL cru, sem model ORM) e estas colunas são novas,
    # então o add direto é seguro em banco novo e em banco com dado legado.
    op.add_column(
        "client_pending_items",
        sa.Column("impacto", sa.String(length=10), nullable=True),
    )
    op.add_column(
        "client_pending_items",
        sa.Column("providencia", sa.String(length=30), nullable=True),
    )


def downgrade() -> None:
    # Reversível com perda apenas do que foi classificado depois do upgrade:
    # nenhuma outra tabela referencia estas colunas e nada é derivado delas.
    op.drop_column("client_pending_items", "providencia")
    op.drop_column("client_pending_items", "impacto")
