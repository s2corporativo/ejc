"""104 — merge da Entrada Universal com o Orquestrador Jurídico.

Revision ID: 104_merge_entrada_orquestrador
Revises: 101_entrada_universal_documentos, 103_fee_proposal

Os PRs #284 e #285 criaram, de forma concorrente, dois ramos válidos a partir de
``100_vw_atividades_enriquecida``. Esta revisão não altera tabelas: apenas
reconcilia o grafo do Alembic para restaurar um único ``head`` canônico.
"""

revision = "104_merge_entrada_orquestrador"
down_revision = (
    "101_entrada_universal_documentos",
    "103_fee_proposal",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Une os dois ramos; não há alteração adicional de schema."""


def downgrade() -> None:
    """Retorna aos dois heads anteriores, sem remover suas estruturas."""
