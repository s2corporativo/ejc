"""Rescan/backfill de SHA-256 de documentos (Épico #1019 A3.2).

Tabelas ``document_hash_rescan_batches`` (controle de lotes de rescan) e
``document_hash_rescan_items`` (resultado por documento), sem qualquer
alteração em tabelas existentes: migration puramente aditiva, compatível
com o gate de deploy (catraca 132+).
"""
from alembic import op
import sqlalchemy as sa

revision = "142_document_hash_rescan"
down_revision = "141_dpt360_diagnostico"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_hash_rescan_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("cliente_id", sa.String(36), nullable=True),
        sa.Column("caso_id", sa.String(36), nullable=True),
        sa.Column("document_ids_json", sa.Text, nullable=True),
        sa.Column("dry_run", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pendente"),
        sa.Column("total_selecionado", sa.Integer, nullable=True),
        sa.Column("total_concluidos", sa.Integer, nullable=True),
        sa.Column("total_erros", sa.Integer, nullable=True),
        sa.Column("total_nao_disponiveis", sa.Integer, nullable=True),
        sa.Column("mecanismo", sa.String(20), nullable=True),
        sa.Column("iniciado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("concluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criado_por", sa.String(36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_doc_hash_rescan_batches_status",
        "document_hash_rescan_batches",
        ["status"],
    )
    op.create_table(
        "document_hash_rescan_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("batch_id", sa.String(36), nullable=False, index=True),
        sa.Column("document_id", sa.String(36), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("motivo", sa.String(60), nullable=True),
        sa.Column("sha256_calculado", sa.String(64), nullable=True, index=True),
        sa.Column("sha256_intake", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("document_hash_rescan_items")
    op.drop_index("ix_doc_hash_rescan_batches_status")
    op.drop_table("document_hash_rescan_batches")
