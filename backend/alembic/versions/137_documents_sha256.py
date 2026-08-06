"""137 — hash de integridade (sha256) no GED (Issue #697)

`documents` é o único caminho de ingestão do EJC sem hash de conteúdo —
document_intake.py, raio_x.py, legal_chat.py e signature.py já têm o
próprio campo sha256/hash_sha256. Sem ele, não há como conferir que o
arquivo baixado é bit-a-bit o que foi enviado (Data Room, Portal do
cliente e comprovante de protocolo dependem do GED).

Coluna NULLABLE de propósito: documentos já ingeridos ficam sem hash até
uma rotina de backfill (Issue própria, fora de escopo aqui) e a via
`POST /documents/drive/upload` (INSERT bruto em SQL) também não foi
alterada nesta migration — grava e mantém o hash e não quebra o schema.

Numeração 137 (não 132): na data desta migration, `MIGRATION_RESERVATIONS.md`
já reservava 132 (`case_parte_pii_encriptado`, PR #746) e 133–135 (reconstrução
do #679, mesmo PR), e a branch `claude/portal-varredura-publicacao-698` já
tinha os arquivos 133–136 criados com outro conteúdo. 137 é o primeiro número
livre de qualquer reserva ou arquivo conhecido nesta data — ver nota completa
em MIGRATION_RESERVATIONS.md.

Revision ID: 137_documents_sha256
Revises: 131_audit_logs_worm
Create Date: 2026-08-06
"""
from alembic import op
import sqlalchemy as sa

revision = "137_documents_sha256"
down_revision = "131_audit_logs_worm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("sha256", sa.String(64), nullable=True),
    )
    op.create_index("ix_documents_sha256", "documents", ["sha256"])


def downgrade() -> None:
    op.drop_index("ix_documents_sha256", table_name="documents")
    op.drop_column("documents", "sha256")
