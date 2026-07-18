"""101 — Entrada Universal de Documentos.

Revision ID: 101_entrada_universal_documentos
Revises: 100_vw_atividades_enriquecida
"""
from alembic import op
import sqlalchemy as sa

revision = "101_entrada_universal_documentos"
down_revision = "100_vw_atividades_enriquecida"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_intake_batches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=True),
        sa.Column("client_id", sa.String(length=36), nullable=True),
        sa.Column("modalidade", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="processando"),
        sa.Column("nivel_prontidao", sa.String(length=32), nullable=True),
        sa.Column("document_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("resultado", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"]),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("case_id", "client_id", "modalidade", "status", "nivel_prontidao", "created_by"):
        op.create_index(f"ix_document_intake_batches_{column}", "document_intake_batches", [column])

    op.create_table(
        "document_intake_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=500), nullable=False),
        sa.Column("extension", sa.String(length=16), nullable=False),
        sa.Column("mimetype", sa.String(length=100), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("source_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_of_document_id", sa.String(length=36), nullable=True),
        sa.Column("extraction_status", sa.String(length=24), nullable=False, server_default="pendente"),
        sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("extraction_meta", sa.JSON(), nullable=True),
        sa.Column("classification", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["document_intake_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("batch_id", "document_id", "sha256", "duplicate_of_document_id", "extraction_status"):
        op.create_index(f"ix_document_intake_items_{column}", "document_intake_items", [column])


def downgrade() -> None:
    op.drop_table("document_intake_items")
    op.drop_table("document_intake_batches")
