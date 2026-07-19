"""092_fix_rag_chave_origem_unique_vigente — corrige índice único de chave_origem
para respeitar o versionamento do RAG (migration 068).

CONTEXTO / BUG
--------------
A migration `006_ingestao_rag` criou:

    CREATE UNIQUE INDEX uq_knowledge_docs_chave_origem
    ON knowledge_docs (chave_origem)
    WHERE chave_origem IS NOT NULL AND deleted_at IS NULL

A migration `068_rag_versionamento` introduziu versionamento (`versao`, `vigente`,
`versao_anterior_id`): ao reingerir um `chave_origem` com conteúdo novo,
`upsert_documento` marca a versão antiga como `vigente=false` (mantendo a mesma
`chave_origem` e `deleted_at` NULL) e INSERE uma nova versão `vigente=true` com a
MESMA `chave_origem`. O índice acima, porém, não considera `vigente` — logo passam
a existir DUAS linhas com a mesma `chave_origem`, `deleted_at IS NULL` → viola o
índice único → IntegrityError, quebrando a atualização de qualquer norma / lei /
jurisprudência.

CORREÇÃO
--------
Substitui o índice por um parcial que só exige unicidade da versão VIGENTE:

    CREATE UNIQUE INDEX uq_knowledge_docs_chave_origem_vigente
    ON knowledge_docs (chave_origem)
    WHERE chave_origem IS NOT NULL AND deleted_at IS NULL AND vigente = true

Versões históricas (`vigente=false`) deixam de disputar unicidade e podem coexistir
com a versão corrente da mesma chave.

SANEAMENTO DE DADOS LEGADOS
---------------------------
Bases já contaminadas podem ter >1 linha `vigente=true` para a mesma `chave_origem`
(fruto do bug), o que faria o CREATE do novo índice falhar. Antes de criar o índice,
mantém `vigente=true` apenas na linha de maior `versao` (desempate por `id`) e
rebaixa as demais para `vigente=false`. Idempotente: em base sã não altera nada.

Downgrade recria exatamente o índice original de 006.
"""
from alembic import op

revision = "092_rag_chave_origem_vigente"
down_revision = "091_atendimento_timeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Saneamento idempotente: no máx. 1 linha vigente por chave_origem.
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY chave_origem
                       ORDER BY versao DESC NULLS LAST, id DESC
                   ) AS rn
            FROM knowledge_docs
            WHERE chave_origem IS NOT NULL
              AND deleted_at IS NULL
              AND vigente = true
        )
        UPDATE knowledge_docs kd
        SET vigente = false
        FROM ranked
        WHERE kd.id = ranked.id
          AND ranked.rn > 1
        """
    )

    # 2) Troca o índice antigo pelo parcial que respeita `vigente`.
    op.execute("DROP INDEX IF EXISTS uq_knowledge_docs_chave_origem")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_docs_chave_origem_vigente
        ON knowledge_docs (chave_origem)
        WHERE chave_origem IS NOT NULL AND deleted_at IS NULL AND vigente = true
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_knowledge_docs_chave_origem_vigente")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_docs_chave_origem
        ON knowledge_docs (chave_origem)
        WHERE chave_origem IS NOT NULL AND deleted_at IS NULL
        """
    )
