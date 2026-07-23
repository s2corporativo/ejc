"""118 — versionamento de documentos (G3)

Revision ID: 118_doc_versionamento
Revises: 117_knowledge_revisao
Create Date: 2026-07-22
"""
from alembic import op
import sqlalchemy as sa

revision = "118_doc_versionamento"
down_revision = "117_knowledge_revisao"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("versao", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "documents",
        sa.Column("versao_grupo_id", sa.String(36), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("versao_anterior_id", sa.String(36), nullable=True),
    )
    op.create_foreign_key(
        "fk_documents_versao_anterior",
        "documents", "documents",
        ["versao_anterior_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_documents_versao_grupo_id", "documents", ["versao_grupo_id"])


def downgrade() -> None:
    op.drop_index("ix_documents_versao_grupo_id", table_name="documents")
    op.drop_constraint("fk_documents_versao_anterior", "documents", type_="foreignkey")
    op.drop_column("documents", "versao_anterior_id")
    op.drop_column("documents", "versao_grupo_id")
    op.drop_column("documents", "versao")
