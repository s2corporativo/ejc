"""162 — registra no Alembic o estado/cache criado historicamente em runtime.

A migration é idempotente para permitir adoção em ambientes que já possuem as
tabelas criadas pelo código antigo. Os serviços continuam com seus guards
temporários; eles podem ser removidos após a primeira promoção desta migration.
"""
from alembic import op

revision = "162_operational_state_tables"
down_revision = "161_fee_estornos"
branch_labels = None
depends_on = None

_TABLES = (
    "indices_bcb_cache",
    "indices_bcb_cache_meta",
    "google_drive_sync_state",
    "infosimples_uso",
    "radar_legislativo_visto",
    "transparencia_cache",
    "backup_drive_state",
)


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS indices_bcb_cache (
            codigo INTEGER NOT NULL,
            data DATE NOT NULL,
            valor NUMERIC(20, 10) NOT NULL,
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (codigo, data)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS indices_bcb_cache_meta (
            codigo INTEGER PRIMARY KEY,
            data_inicial DATE NOT NULL,
            data_final DATE NOT NULL,
            consultado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
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
    """)
    op.execute("""
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
    """)
    op.execute("""
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
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS transparencia_cache (
            id VARCHAR(36) PRIMARY KEY,
            dia DATE NOT NULL,
            base VARCHAR(80) NOT NULL,
            cnpj VARCHAR(32) NOT NULL,
            resultado JSONB NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS backup_drive_state (
            id SMALLINT PRIMARY KEY DEFAULT 1,
            last_run_at TIMESTAMPTZ NULL,
            last_status TEXT NULL,
            last_error TEXT NULL,
            last_origem TEXT NULL,
            duracao_segundos DOUBLE PRECISION NULL,
            detalhes JSONB NULL,
            offsite_ok BOOLEAN NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_infosimples_uso_dia ON infosimples_uso (dia)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_infosimples_uso_cache ON infosimples_uso (dia, caminho, parametros_hash)")


def downgrade() -> None:
    # O downgrade é explícito e reversível apenas para schema; os caches/estados
    # devem ser exportados antes de executá-lo em ambiente real.
    for table in reversed(_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table}")
