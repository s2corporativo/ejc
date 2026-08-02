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

Semântica: incrementa quando a execução termina em sucesso pleno sem NADA
recebido nem processado (run zerado de verdade); zera quando a execução produz
algo novo OU quando recebe e processa registros ainda que inalterados (ingestão
idempotente saudável — ex.: reprocessar um catálogo fixo). Execução com status
`erro` ou `parcial` não mexe no contador. Fontes existentes começam em 0 — sem
backfill heurístico, porque não há histórico de execuções para reconstruir.

A segunda coluna, `ja_produziu`, é o marcador VITALÍCIO de que a fonte já
trouxe registro novo alguma vez. `registros_total` é sobrescrito a cada
execução, então uma consulta legítima com zero resultados apagaria o histórico
e faria uma fonte produtiva virar `nunca_produziu` no painel. Backfill: fontes
com registros no estado atual já produziram.

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

# Tabela e coluna vão como LITERAIS, não como constantes de módulo:
# `tests/test_schema_dr_parity.py` confere a paridade ORM × migrations lendo
# estes arquivos por AST, e só reconhece `ast.Constant`. Um nome de variável é
# invisível para o scanner, e a coluna apareceria como "sem migration".


def upgrade() -> None:
    op.add_column(
        "fontes_ingestao",
        sa.Column(
            "execucoes_zeradas_consecutivas",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "fontes_ingestao",
        sa.Column(
            "ja_produziu",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # Backfill: o estado atual é a única evidência disponível — fonte com
    # registros na última execução comprovadamente já produziu. Fonte zerada
    # hoje mas produtiva no passado não é recuperável (o total é sobrescrito),
    # e ficará marcada na primeira execução que trouxer algo.
    op.execute(
        "UPDATE fontes_ingestao SET ja_produziu = TRUE "
        "WHERE registros_total > 0 OR registros_novos > 0"
    )


def downgrade() -> None:
    op.drop_column("fontes_ingestao", "ja_produziu")
    op.drop_column("fontes_ingestao", "execucoes_zeradas_consecutivas")
