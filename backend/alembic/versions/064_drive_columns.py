"""059 — colunas do Google Drive em documents e cases

Os endpoints /documents/drive/* (upload/link/download/delete) e o
_get_or_create_case_folder referenciavam colunas que NUNCA existiram no
schema (`documents.drive_file_id`, `documents.drive_link`,
`cases.drive_folder_id`) — qualquer chamada quebrava em runtime
(UndefinedColumn). Esta migração cria essas 3 colunas.

As demais referências do código Drive (nome/tamanho/created_by) foram
ALINHADAS às colunas já existentes (titulo/filename/size_bytes/uploaded_by)
no próprio router — não se criam colunas duplicadas.

IDEMPOTENTE: ADD COLUMN IF NOT EXISTS.

Revision ID: 059_drive_columns
Revises: 058_workflow_sla_atrasado
Create Date: 2026-07-03
"""
from alembic import op

revision = "064_drive_columns"
down_revision = "063_workflow_sla_atrasado"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS drive_file_id VARCHAR(128)"
    )
    op.execute(
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS drive_link VARCHAR(500)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_documents_drive_file_id "
        "ON documents (drive_file_id)"
    )
    op.execute(
        "ALTER TABLE cases ADD COLUMN IF NOT EXISTS drive_folder_id VARCHAR(128)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_documents_drive_file_id")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS drive_file_id")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS drive_link")
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS drive_folder_id")
