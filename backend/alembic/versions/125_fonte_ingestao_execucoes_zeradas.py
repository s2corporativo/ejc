"""Contador de execuções consecutivas sem produzir nada, por fonte de ingestão.

Por que esta coluna existe
──────────────────────────
O monitoramento das fontes afere CADÊNCIA (`ultima_execucao`, `ultimo_status`) e
não RESULTADO. Um job que roda pontualmente e entrega zero é indistinguível de um
saudável — foi assim que a captura do DJEN reportou "sucesso" por meses sem nunca
ter registrado uma única intimação.

`registros_novos` guarda apenas a última execução, então "rodou 12 vezes seguidas
sem trazer nada" não é derivável do estado atual: precisa ser contado no momento
em que a execução termina. É o que esta coluna faz.

Semântica: incrementa quando a execução termina sem erro e sem registros novos;
zera assim que uma execução produz algo. Fontes existentes começam em 0 — sem
backfill heurístico, porque não há histórico de execuções para reconstruir.

Revision ID: 125_fonte_execucoes_zeradas
Revises: 124_dataroom_public_hardening
Create Date: 2026-08-02
"""

from alembic import op
import sqlalchemy as sa

revision = "125_fonte_execucoes_zeradas"
down_revision = "124_dataroom_public_hardening"
branch_labels = None
depends_on = None

_TABELA = "fontes_ingestao"
_COLUNA = "execucoes_zeradas_consecutivas"


def upgrade() -> None:
    op.add_column(
        _TABELA,
        sa.Column(
            _COLUNA,
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column(_TABELA, _COLUNA)
