"""076 — Índices em FKs de caminho quente (controle de acesso e vínculos).

O Postgres NÃO cria índice automático para FOREIGN KEY. A auditoria de banco
apontou FKs sem índice usadas em filtros frequentes — a mais relevante é
`cases.advogado_auxiliar_id`, usada no gate de visibilidade por advogado em
vários routers (fees, legal_docs, documents, search): sem índice, cada filtro
por auxiliar faz seq scan em `cases`.

Adiciona índices B-tree simples nas FKs de caminho quente. Puramente aditivo e
não-destrutivo: `CREATE INDEX IF NOT EXISTS` (idempotente, seguro em rebase de
deploy) e `DROP INDEX IF EXISTS` no downgrade. Nenhum dado é tocado.

Escopo deliberadamente enxuto: só FKs com uso real em filtro/join. FKs de
auditoria (created_by, aprovado_por, …) ficam de fora — índice ali é opcional
e o volume (escritório pequeno) não justifica.

Revision ID: 076_fk_hot_path_indexes
Revises: 075_fk_partial_unique_dtnasc
"""
from alembic import op

revision = "076_fk_hot_path_indexes"
down_revision = "075_fk_partial_unique_dtnasc"
branch_labels = None
depends_on = None


# (nome_do_indice, tabela, coluna) — FKs de caminho quente confirmadas.
_INDICES = [
    ("ix_cases_advogado_auxiliar_id",      "cases",       "advogado_auxiliar_id"),
    ("ix_clients_responsavel_id",          "clients",     "responsavel_id"),
    ("ix_case_partes_client_id",           "case_partes", "client_id"),
    ("ix_data_rooms_case_id",              "data_rooms",  "case_id"),
    ("ix_data_rooms_client_id",            "data_rooms",  "client_id"),
    ("ix_processes_processo_principal_id", "processes",   "processo_principal_id"),
]


def upgrade() -> None:
    for nome, tabela, coluna in _INDICES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {nome} ON {tabela} ({coluna})")


def downgrade() -> None:
    for nome, _tabela, _coluna in _INDICES:
        op.execute(f"DROP INDEX IF EXISTS {nome}")
