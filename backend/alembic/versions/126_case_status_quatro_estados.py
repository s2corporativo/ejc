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

TÉCNICA — desvio por text, não renomeação de tipos: a primeira versão usava
ALTER TYPE ... RENAME + conversão direta enum→enum, e o Postgres reprovou com
"operator does not exist: casestatus = casestatus_old" — com os dois enums
coexistindo, a coerção no USING resolve para o tipo errado. A receita robusta
rebaixa a coluna para text, converte os valores como texto, recria o tipo do
zero e sobe de volta: em nenhum momento dois enums coexistem. `casestatus` é
usado apenas por cases.status (conferido em 001_inicial e nos models), então o
DROP TYPE não tem outros dependentes.

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


def _trocar_enum(valores_novos: str, conversao_sql: str, default_novo: str) -> None:
    """Desvio por text: coluna vira text → valores convertidos → tipo recriado."""
    op.execute("ALTER TABLE cases ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TABLE cases ALTER COLUMN status TYPE text USING status::text")
    op.execute(conversao_sql)
    op.execute("DROP TYPE casestatus")
    op.execute(f"CREATE TYPE casestatus AS ENUM ({valores_novos})")
    op.execute(
        "ALTER TABLE cases ALTER COLUMN status TYPE casestatus "
        "USING status::casestatus"
    )
    op.execute(
        f"ALTER TABLE cases ALTER COLUMN status SET DEFAULT '{default_novo}'"
    )


def upgrade() -> None:
    _trocar_enum(
        _NOVOS,
        """
        UPDATE cases SET status = CASE status
            WHEN 'triagem'  THEN 'aberto'
            WHEN 'ativo'    THEN 'em_instrucao'
            WHEN 'suspenso' THEN 'aberto'
            WHEN 'acordo'   THEN 'encerrado'
            ELSE status
        END
        """,
        "aberto",
    )


def downgrade() -> None:
    _trocar_enum(
        _ANTIGOS,
        """
        UPDATE cases SET status = CASE status
            WHEN 'aberto'       THEN 'triagem'
            WHEN 'em_instrucao' THEN 'ativo'
            WHEN 'em_producao'  THEN 'ativo'
            WHEN 'protocolado'  THEN 'ativo'
            ELSE status
        END
        """,
        "triagem",
    )
