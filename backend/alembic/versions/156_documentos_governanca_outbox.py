"""Governança documental, estados de processamento e outbox de storage.

Revision ID: 156_documentos_governanca_outbox
Revises: 155_indices_listagem_espinha
Create Date: 2026-09-02

Migration expand-only: não remove nem reinterpreta dados existentes. Campos de
estado permanecem NULL para legado quando não há evidência suficiente para
atribuir um status. ``legal_hold`` nasce false porque representa somente bloqueio
explicitamente aplicado a partir desta versão; nenhum prazo legal é inventado.
"""
from alembic import op
import sqlalchemy as sa

revision = "156_documentos_governanca_outbox"
down_revision = "155_indices_listagem_espinha"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("malware_scan_status", sa.String(length=20), nullable=True))
    op.add_column("documents", sa.Column("malware_scanned_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("analysis_status", sa.String(length=20), nullable=True))
    op.add_column("documents", sa.Column("analysis_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("analysis_error_code", sa.String(length=60), nullable=True))
    op.add_column("documents", sa.Column("analysis_source_sha256", sa.String(length=64), nullable=True))

    op.add_column("documents", sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "documents",
        sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("documents", sa.Column("legal_hold_reason", sa.Text(), nullable=True))
    op.add_column(
        "documents",
        sa.Column(
            "legal_hold_set_by",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("documents", sa.Column("legal_hold_set_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("documents", sa.Column("integrity_status", sa.String(length=20), nullable=True))
    op.add_column("documents", sa.Column("integrity_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("rag_status", sa.String(length=20), nullable=True))
    op.add_column("documents", sa.Column("rag_knowledge_doc_id", sa.String(length=36), nullable=True))
    op.add_column("documents", sa.Column("rag_indexed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("rag_source_sha256", sa.String(length=64), nullable=True))

    op.create_index("ix_documents_legal_hold", "documents", ["legal_hold"], unique=False)
    op.create_index("ix_documents_retention_until", "documents", ["retention_until"], unique=False)
    op.create_index("ix_documents_analysis_status", "documents", ["analysis_status"], unique=False)
    op.create_index("ix_documents_malware_scan_status", "documents", ["malware_scan_status"], unique=False)
    op.create_index("ix_documents_rag_status", "documents", ["rag_status"], unique=False)

    op.create_table(
        "document_storage_operations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("operation_key", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("storage_kind", sa.String(length=20), nullable=False),
        sa.Column("storage_locator", sa.String(length=1000), nullable=False),
        sa.Column("drive_file_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(length=60), nullable=True),
        sa.Column("requested_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("operation_key", name="uq_document_storage_operations_key"),
    )
    op.create_index(
        "ix_document_storage_operations_operation_key",
        "document_storage_operations",
        ["operation_key"],
        unique=True,
    )
    op.create_index(
        "ix_document_storage_operations_document_id",
        "document_storage_operations",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_storage_operations_status",
        "document_storage_operations",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_document_storage_operations_status", table_name="document_storage_operations")
    op.drop_index("ix_document_storage_operations_document_id", table_name="document_storage_operations")
    op.drop_index("ix_document_storage_operations_operation_key", table_name="document_storage_operations")
    op.drop_table("document_storage_operations")

    op.drop_index("ix_documents_rag_status", table_name="documents")
    op.drop_index("ix_documents_malware_scan_status", table_name="documents")
    op.drop_index("ix_documents_analysis_status", table_name="documents")
    op.drop_index("ix_documents_retention_until", table_name="documents")
    op.drop_index("ix_documents_legal_hold", table_name="documents")

    op.drop_column("documents", "rag_source_sha256")
    op.drop_column("documents", "rag_indexed_at")
    op.drop_column("documents", "rag_knowledge_doc_id")
    op.drop_column("documents", "rag_status")
    op.drop_column("documents", "integrity_verified_at")
    op.drop_column("documents", "integrity_status")

    op.drop_column("documents", "legal_hold_set_at")
    op.drop_column("documents", "legal_hold_set_by")
    op.drop_column("documents", "legal_hold_reason")
    op.drop_column("documents", "legal_hold")
    op.drop_column("documents", "retention_until")

    op.drop_column("documents", "analysis_source_sha256")
    op.drop_column("documents", "analysis_error_code")
    op.drop_column("documents", "analysis_updated_at")
    op.drop_column("documents", "analysis_status")
    op.drop_column("documents", "malware_scanned_at")
    op.drop_column("documents", "malware_scan_status")
