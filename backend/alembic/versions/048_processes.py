"""048_processes — BASELINE consolidado do schema EJC

Revision ID: 048_processes
Revises:
Create Date: 2026-06-29

Materializa a revisão-base que a cadeia 049/050 sempre referenciou: o arquivo
``048_processes`` era citado por ``049.down_revision`` mas NUNCA existiu — o
Alembic ficava inoperante (cadeia quebrada). As migrations 001–048 originais
foram perdidas; este baseline as substitui de forma consolidada.

Estratégia (idempotente e segura contra banco já existente):
  1. CREATE EXTENSION IF NOT EXISTS vector  (pgvector — colunas Vector do RAG)
  2. Base.metadata.create_all(checkfirst=True) — cria TODAS as tabelas dos
     modelos ORM que ainda não existam (não recria nem altera as existentes).
  3. CREATE TABLE IF NOT EXISTS processes — entidade SQL-crua (sem modelo ORM),
     reconstruída a partir de routers/processes.py e services/processo_service.py.

⚠️ PRODUÇÃO: o banco de produção JÁ possui este schema. NÃO rode ``alembic
upgrade`` cru sem antes verificar ``SELECT version_num FROM alembic_version`` e,
no cenário normal, fazer ``alembic stamp 050_novos_modulos`` (marca como
aplicado sem executar). Tudo aqui é IF NOT EXISTS / checkfirst, mas o stamp é a
rota recomendada. Ver RELATORIO_FASE2_BANCO_2026-06-29.md.

⚠️ A tabela ``processes`` é uma RECONSTRUÇÃO a partir do código; valide contra
``pg_dump --schema-only -t processes`` da produção antes de confiar nela para
disaster recovery.
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "048_processes"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1. pgvector — necessário antes das colunas Vector(768) do KnowledgeChunk.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. Todas as tabelas dos modelos ORM (checkfirst=True → não toca existentes).
    #    env.py já importou todos os submódulos de app.models, então Base.metadata
    #    está completo neste ponto.
    from app.core.database import Base
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=bind, checkfirst=True)

    # 3. processes — 1 Caso : N Processos (SQL cru, padrão do projeto, sem ORM).
    op.execute("""
    CREATE TABLE IF NOT EXISTS processes (
        id                    VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
        case_id               VARCHAR(36)  NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
        numero_cnj            VARCHAR(30),
        instancia             VARCHAR(40),
        tribunal              VARCHAR(40),
        comarca               VARCHAR(120),
        vara                  VARCHAR(120),
        classe                VARCHAR(150),
        fase                  VARCHAR(60),
        tipo                  VARCHAR(40)  NOT NULL DEFAULT 'judicial',
        processo_principal_id VARCHAR(36)  REFERENCES processes(id) ON DELETE SET NULL,
        is_principal          BOOLEAN      NOT NULL DEFAULT FALSE,
        valor_causa           NUMERIC(14,2),
        status                VARCHAR(40)  NOT NULL DEFAULT 'ativo',
        created_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        updated_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        deleted_at            TIMESTAMPTZ
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_processes_case_id ON processes(case_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_processes_principal ON processes(case_id, is_principal)")


def downgrade() -> None:
    # Baseline consolidado: não destrói o schema inteiro.
    raise NotImplementedError("Baseline inicial (048_processes) não suporta downgrade.")
