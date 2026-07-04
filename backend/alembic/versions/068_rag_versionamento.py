"""068_rag_versionamento — versionamento de documentos da base RAG

Revision ID: 068_rag_versionamento
Revises: 067_v4_dataroom_teses
Create Date: 2026-07-04

Hoje `upsert_documento` (ingestion_service.py) e `_ingerir_texto` (routers/rag.py)
SOBRESCREVEM o registro existente quando o mesmo `chave_origem`/hash é reingerido:
os chunks antigos são apagados e o `KnowledgeDoc` é atualizado in-place. Para uso
jurídico isso é arriscado — se um tribunal muda de entendimento ou uma norma é
revogada, perdemos a versão anterior sem rastro, e citações antigas já usadas em
petições ficam órfãs (sem como auditar o texto que embasou a peça na época).

Esta migration adiciona versionamento a `knowledge_docs`:
  - `versao`             : Integer, default 1. Incrementa a cada reingestão do
                           mesmo `chave_origem` que muda de conteúdo.
  - `vigente`             : Boolean, default true. Só documentos vigentes entram
                           na busca RAG por padrão (histórico fica preservado,
                           mas oculto salvo pedido explícito).
  - `versao_anterior_id`  : FK nullable para knowledge_docs.id — encadeia a
                           versão nova à versão que ela substituiu.

ADITIVO PURO e IDEMPOTENTE (mesmo padrão de 055_rag_isolation): ADD COLUMN IF NOT
EXISTS, índice em `vigente`, FK criada apenas se ainda não existir. Nenhum dado
existente é apagado; documentos já presentes recebem versao=1 / vigente=true via
DEFAULT — continuam recuperáveis normalmente.

Downgrade remove a FK, o índice e as três colunas (reversível).
"""
from alembic import op

revision = "068_rag_versionamento"
down_revision = "067_v4_dataroom_teses"
branch_labels = None
depends_on = None

_FK_NAME = "fk_knowledge_docs_versao_anterior_id"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE knowledge_docs ADD COLUMN IF NOT EXISTS versao INTEGER NOT NULL DEFAULT 1"
    )
    op.execute(
        "ALTER TABLE knowledge_docs ADD COLUMN IF NOT EXISTS vigente BOOLEAN NOT NULL DEFAULT true"
    )
    op.execute(
        "ALTER TABLE knowledge_docs ADD COLUMN IF NOT EXISTS versao_anterior_id VARCHAR(36)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_docs_vigente ON knowledge_docs(vigente)"
    )
    # FK auto-referenciada (versão nova → versão anterior). ADD CONSTRAINT não
    # suporta IF NOT EXISTS no Postgres; checa via information_schema antes.
    op.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = '{_FK_NAME}'
                  AND table_name = 'knowledge_docs'
            ) THEN
                ALTER TABLE knowledge_docs
                    ADD CONSTRAINT {_FK_NAME}
                    FOREIGN KEY (versao_anterior_id)
                    REFERENCES knowledge_docs(id)
                    ON DELETE SET NULL;
            END IF;
        END
        $$;
    """)


def downgrade() -> None:
    op.execute(f"ALTER TABLE knowledge_docs DROP CONSTRAINT IF EXISTS {_FK_NAME}")
    op.execute("DROP INDEX IF EXISTS ix_knowledge_docs_vigente")
    op.execute("ALTER TABLE knowledge_docs DROP COLUMN IF EXISTS versao_anterior_id")
    op.execute("ALTER TABLE knowledge_docs DROP COLUMN IF EXISTS vigente")
    op.execute("ALTER TABLE knowledge_docs DROP COLUMN IF EXISTS versao")
