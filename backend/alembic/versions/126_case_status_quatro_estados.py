"""Quatro estados de caso no lugar do vocabulário misto (Bloco 3, decisão b).

Decisão do titular em 2026-08-02 (docs/DESENHO_ENTRADA_UNICA_E_CASO_WORKSPACE.md):
o enum `casestatus` é migrado DE VERDADE — um vocabulário só no banco e na tela,
em vez de derivar estados na apresentação e conviver com dois dicionários, que é
a classe de confusão que o Bloco 1 corrigiu em outra frente.

Valores novos:  aberto · em_instrucao · em_producao · protocolado · encerrado · arquivado
Conversão:      triagem → aberto        (existe, tem cliente e fatos)
                ativo   → em_instrucao  (juntando documentos e provas)
                suspenso → aberto       (nenhuma linha em produção; sem perda)
                acordo  → encerrado     (acordo é desfecho; nenhuma linha em produção)
`encerrado` e `arquivado` permanecem: desfecho e guarda são coisas distintas e
os endpoints de arquivar/lixeira dependem da distinção.

Janela: nenhum caso real passou da triagem — 8 casos em `triagem` e 1
`arquivado` são o custo total da conversão. Depois do lançamento este custo
muda de ordem de grandeza; é por isso que a migração acontece agora.

O downgrade é estruturalmente reversível mas SEMÂNTICAMENTE lossy: os três
estados de trabalho (em_instrucao/em_producao/protocolado) colapsam de volta em
`ativo`, e `aberto` vira `triagem`. Aceitável porque só se volta atrás antes da
operação começar — depois dela, corrige-se com migration nova, nunca com
downgrade.

Revision ID: 126_case_status_quatro_estados
Revises: 124_dataroom_public_hardening
Create Date: 2026-08-02
"""

from alembic import op

revision = "126_case_status_quatro_estados"
# NOTA DE COORDENAÇÃO: o head da main é 124. O PR #624 reserva a 125
# (fonte_execucoes_zeradas) e ainda não foi mesclado — a governança não permite
# empilhar branches, então esta migration nasce encadeada na 124. Assim que o
# #624 for mesclado, este down_revision DEVE virar "125_fonte_execucoes_zeradas"
# (mudança de uma linha, registrada em MIGRATION_RESERVATIONS.md).
down_revision = "124_dataroom_public_hardening"
branch_labels = None
depends_on = None

_NOVOS = "'aberto','em_instrucao','em_producao','protocolado','encerrado','arquivado'"
_ANTIGOS = "'triagem','ativo','suspenso','acordo','encerrado','arquivado'"


def upgrade() -> None:
    op.execute("ALTER TYPE casestatus RENAME TO casestatus_old")
    op.execute(f"CREATE TYPE casestatus AS ENUM ({_NOVOS})")
    op.execute("ALTER TABLE cases ALTER COLUMN status DROP DEFAULT")
    op.execute(
        """
        ALTER TABLE cases ALTER COLUMN status TYPE casestatus USING (
            CASE status::text
                WHEN 'triagem'  THEN 'aberto'
                WHEN 'ativo'    THEN 'em_instrucao'
                WHEN 'suspenso' THEN 'aberto'
                WHEN 'acordo'   THEN 'encerrado'
                ELSE status::text
            END
        )::casestatus
        """
    )
    op.execute("ALTER TABLE cases ALTER COLUMN status SET DEFAULT 'aberto'")
    op.execute("DROP TYPE casestatus_old")


def downgrade() -> None:
    op.execute("ALTER TYPE casestatus RENAME TO casestatus_old")
    op.execute(f"CREATE TYPE casestatus AS ENUM ({_ANTIGOS})")
    op.execute("ALTER TABLE cases ALTER COLUMN status DROP DEFAULT")
    op.execute(
        """
        ALTER TABLE cases ALTER COLUMN status TYPE casestatus USING (
            CASE status::text
                WHEN 'aberto'       THEN 'triagem'
                WHEN 'em_instrucao' THEN 'ativo'
                WHEN 'em_producao'  THEN 'ativo'
                WHEN 'protocolado'  THEN 'ativo'
                ELSE status::text
            END
        )::casestatus
        """
    )
    op.execute("ALTER TABLE cases ALTER COLUMN status SET DEFAULT 'triagem'")
    op.execute("DROP TYPE casestatus_old")
