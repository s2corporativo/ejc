"""074 — remove valor 'licitacao_recurso' de AdminTipo (auditoria licitação)

Contexto:
    A auditoria remove todas as referências a licitação do EJC. O valor de
    enum `licitacao_recurso` ("Lei 14.133/21 art. 165") foi retirado da enum
    Python `AdminTipo` (backend/app/models/especializado.py) e do formulário
    do frontend. Nenhum código novo cria registros com esse valor.

Storage:
    A coluna `admin_cases.tipo` é VARCHAR (`sa.String(50)`) — ver migration
    010_ramos_juridicos.py. NÃO existe tipo ENUM nativo no Postgres para
    AdminTipo, portanto NÃO há `ALTER TYPE`/`DROP VALUE`. Basta reatribuir os
    dados existentes.

Ação (Regra 8 — não corromper dados):
    Reatribui linhas legadas com tipo = 'licitacao_recurso' para o valor
    genérico seguro 'outro_admin' (que existe na enum AdminTipo). Idempotente.

Revision ID: 074_remove_licitacao_admin_tipo
Revises: 073_provas
"""
from alembic import op

revision = "074_remove_licitacao_admin_tipo"
down_revision = "073_provas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Reatribui casos administrativos legados de licitação para 'outro_admin'.
    # Coluna VARCHAR — não há tipo enum nativo a alterar.
    op.execute(
        "UPDATE admin_cases "
        "SET tipo = 'outro_admin' "
        "WHERE tipo = 'licitacao_recurso'"
    )


def downgrade() -> None:
    # Migration de DADOS irreversível por natureza: após a reatribuição não é
    # possível distinguir quais linhas 'outro_admin' eram originalmente
    # 'licitacao_recurso'. Como a coluna é VARCHAR e o schema não muda, o
    # downgrade é um no-op seguro (não deixa o banco em estado inconsistente).
    pass
