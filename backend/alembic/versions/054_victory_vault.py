"""054 — Victory Vault: persistência real (teses_vitoriosas, modelos_documentos)

Antes o Victory Vault era um store in-memory (lista Python carregada de JSON mock):
todo POST se perdia no restart. Esta migration cria as tabelas reais e o
app/core/victory_vault.py passa a ler/gravar no banco (auto-seed do mock na 1ª
vez que a tabela estiver vazia, preservando o conteúdo de demonstração).

Idempotente (CREATE TABLE IF NOT EXISTS). Downgrade dropa as tabelas (feature nova,
sem dados legados em produção).

Revision ID: 054_victory_vault
Revises: 053_reconcile_schema
Create Date: 2026-06-28
"""
from alembic import op

revision = "054_victory_vault"
down_revision = "053_reconcile_schema"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE IF NOT EXISTS teses_vitoriosas (
        id            VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
        titulo        TEXT         NOT NULL,
        ementa        TEXT         NOT NULL,
        area_juridica VARCHAR(80)  NOT NULL,
        data_vitoria  VARCHAR(20),
        link          TEXT,
        created_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        deleted_at    TIMESTAMP WITH TIME ZONE
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_teses_vitoriosas_area ON teses_vitoriosas (area_juridica);")

    op.execute("""
    CREATE TABLE IF NOT EXISTS modelos_documentos (
        id                VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
        tipo_documento    VARCHAR(80)  NOT NULL,
        area_juridica     VARCHAR(80)  NOT NULL,
        conteudo_template TEXT         NOT NULL,
        descricao         TEXT,
        created_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        deleted_at        TIMESTAMP WITH TIME ZONE
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_modelos_documentos_tipo ON modelos_documentos (tipo_documento, area_juridica);")


def downgrade():
    op.execute("DROP TABLE IF EXISTS modelos_documentos;")
    op.execute("DROP TABLE IF EXISTS teses_vitoriosas;")
