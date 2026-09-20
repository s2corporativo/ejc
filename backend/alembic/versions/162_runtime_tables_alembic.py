"""162 — adota tabelas de estado/cache no Alembic e fecha DDL de runtime.

Objetivo:
- tornar o schema PostgreSQL determinístico antes da redução de privilégios do
  papel usado pela aplicação;
- criar, de forma idempotente, tabelas que historicamente eram abertas por
  CREATE TABLE IF NOT EXISTS dentro dos services;
- preservar tabelas/dados já existentes em produção;
- adicionar apenas dois índices de FK priorizados por volume medido.

Revision ID: 162_runtime_tables_alembic
Revises: 161_fee_estornos
"""
from alembic import op

revision = "162_runtime_tables_alembic"
down_revision = "161_fee_estornos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS google_drive_sync_state (
            folder_id TEXT PRIMARY KEY,
            last_start_page_token TEXT NULL,
            last_sync_at TIMESTAMPTZ NULL,
            last_status TEXT NULL,
            last_error TEXT NULL,
            total_files_seen INTEGER NOT NULL DEFAULT 0,
            total_files_ingested INTEGER NOT NULL DEFAULT 0,
            total_files_skipped INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS transparencia_cache (
            id VARCHAR(36) PRIMARY KEY,
            dia DATE NOT NULL,
            base VARCHAR(16) NOT NULL,
            cnpj CHAR(14) NOT NULL,
            resultado JSONB NULL,
            user_id VARCHAR(36) NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_transparencia_cache_lookup
        ON transparencia_cache (dia, base, cnpj)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS indices_bcb_cache (
            codigo INTEGER NOT NULL,
            data DATE NOT NULL,
            valor NUMERIC(20, 10) NOT NULL,
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (codigo, data)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS indices_bcb_cache_meta (
            codigo INTEGER PRIMARY KEY,
            data_inicial DATE NOT NULL,
            data_final DATE NOT NULL,
            consultado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS radar_legislativo_visto (
            fonte VARCHAR(20) NOT NULL,
            id_externo VARCHAR(80) NOT NULL,
            tipo VARCHAR(30),
            numero INTEGER,
            ano INTEGER,
            ementa TEXT,
            url TEXT,
            data_apresentacao VARCHAR(30),
            ultima_tramitacao TEXT,
            termo VARCHAR(200),
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (fonte, id_externo)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS backup_drive_state (
            id SMALLINT PRIMARY KEY DEFAULT 1,
            last_run_at TIMESTAMPTZ NULL,
            last_status TEXT NULL,
            last_error TEXT NULL,
            last_origem TEXT NULL,
            duracao_segundos DOUBLE PRECISION NULL,
            detalhes JSONB NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            offsite_ok BOOLEAN NULL
        )
        """
    )
    # Instalações antigas podem ter a tabela prévia à coluna offsite_ok.
    op.execute(
        """
        ALTER TABLE backup_drive_state
        ADD COLUMN IF NOT EXISTS offsite_ok BOOLEAN NULL
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS infosimples_uso (
            id VARCHAR(36) PRIMARY KEY,
            dia DATE NOT NULL,
            caminho TEXT NOT NULL,
            parametros_hash CHAR(64) NOT NULL,
            code INTEGER NULL,
            resultado JSONB NULL,
            user_id VARCHAR(36) NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_infosimples_uso_dia
        ON infosimples_uso (dia)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_infosimples_uso_cache
        ON infosimples_uso (dia, caminho, parametros_hash)
        """
    )

    # Auditoria de produção 19/09/2026: únicas FKs sem índice de apoio com
    # volume atual material. Demais candidatas permanecem sem mudança até
    # haver cardinalidade/uso que justifique custo adicional de escrita.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_knowledge_docs_versao_anterior_id
        ON knowledge_docs (versao_anterior_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_diario_oficial_alertas_keyword_id
        ON diario_oficial_alertas (keyword_id)
        """
    )


def downgrade() -> None:
    # As tabelas acima já podiam existir e conter dados ANTES desta migration,
    # porque eram criadas pelos services. Derrubá-las no downgrade apagaria
    # estado/cache operacional preexistente. Rollback seguro remove somente os
    # dois índices novos de otimização; as tabelas adotadas permanecem.
    op.execute("DROP INDEX IF EXISTS ix_diario_oficial_alertas_keyword_id")
    op.execute("DROP INDEX IF EXISTS ix_knowledge_docs_versao_anterior_id")
