"""DJEN: remove a unicidade global de comunicacao_id_externo (passo 2 de 2).

Antes, ``comunicacao_id_externo`` era UNIQUE global: a mesma comunicação
destinada a dois advogados do escritório só era entregue ao primeiro que a
capturasse. A unicidade passa a ser por (comunicacao_id_externo, advogado_id),
criada na 169. Aqui o índice único antigo é substituído por um índice comum de
mesmo nome (a busca por id externo continua indexada).

Relaxa uma restrição: nenhum dado é alterado ou removido. O downgrade recusa-se
a reintroduzir a unicidade global se já houver comunicação replicada entre
advogados (evita perda de dado).

Revision ID: 170_djen_remove_unicidade_global
Revises: 169_djen_multi_advogado
Create Date: 2026-10-02
"""
from alembic import op

revision = "170_djen_remove_unicidade_global"
down_revision = "169_djen_multi_advogado"
branch_labels = None
depends_on = None

# Remoção deliberada de índice UNIQUE (relaxamento), substituído no mesmo passo.
deployment_policy = "human_reviewed_drop"

_INDICE = "ix_djen_comunicacoes_comunicacao_id_externo"


def upgrade() -> None:
    op.drop_index(_INDICE, table_name="djen_comunicacoes")
    op.create_index(_INDICE, "djen_comunicacoes", ["comunicacao_id_externo"], unique=False)


def downgrade() -> None:
    conn = op.get_bind()
    repetidas = conn.exec_driver_sql(
        "SELECT count(*) FROM (SELECT 1 FROM djen_comunicacoes "
        "GROUP BY comunicacao_id_externo HAVING count(*) > 1) t"
    ).scalar()
    if repetidas:
        raise RuntimeError(
            "downgrade 170 recusado: existem comunicações DJEN replicadas entre "
            "advogados; reintroduzir a unicidade global descartaria dados. "
            "Procedimento seguro (com reserva das réplicas): "
            "docs/operacao/ROLLBACK_DJEN_169_170.md"
        )
    op.drop_index(_INDICE, table_name="djen_comunicacoes")
    op.create_index(_INDICE, "djen_comunicacoes", ["comunicacao_id_externo"], unique=True)
