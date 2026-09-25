"""Proveniência processual e identidade canônica de partes.

Revision ID: 163_process_provenance_party_identity
Revises: 162_case_financial_classification
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "163_process_provenance_party_identity"
down_revision = "162_case_financial_classification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("processes", sa.Column("data_ajuizamento", sa.Date(), nullable=True))
    op.create_table(
        "party_entities",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("client_id", sa.String(length=36), sa.ForeignKey("clients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entity_type", sa.String(length=16), nullable=False, server_default="desconhecido"),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("cpf_cnpj_hash", sa.String(length=64), nullable=True),
        sa.Column("aliases", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("entity_type IN ('PF','PJ','desconhecido')", name="ck_party_entities_type"),
    )
    op.create_index("ix_party_entities_normalized_name", "party_entities", ["normalized_name"])
    op.create_index(
        "ux_party_entities_doc_hash_active", "party_entities", ["cpf_cnpj_hash"],
        unique=True,
        postgresql_where=sa.text("cpf_cnpj_hash IS NOT NULL AND deleted_at IS NULL"),
    )
    op.create_index(
        "ux_party_entities_client_active", "party_entities", ["client_id"],
        unique=True,
        postgresql_where=sa.text("client_id IS NOT NULL AND deleted_at IS NULL"),
    )
    op.add_column(
        "case_partes",
        sa.Column("party_entity_id", sa.String(length=36), sa.ForeignKey("party_entities.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_case_partes_party_entity_id", "case_partes", ["party_entity_id"])

    op.create_table(
        "process_data_provenance",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("process_id", sa.String(length=36), sa.ForeignKey("processes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field_name", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("source_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("value_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence", sa.String(length=20), nullable=True),
        sa.Column("confirmed_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "source_type IN ('usuario','documento','datajud','djen','tribunal','importacao','entrada_unica','sistema')",
            name="ck_process_data_provenance_source",
        ),
    )
    op.create_index("ix_process_data_provenance_process", "process_data_provenance", ["process_id"])
    op.create_index("ix_process_data_provenance_field", "process_data_provenance", ["field_name"])
    op.create_index("ix_process_data_provenance_source", "process_data_provenance", ["source_type"])


def downgrade() -> None:
    op.drop_index("ix_process_data_provenance_source", table_name="process_data_provenance")
    op.drop_index("ix_process_data_provenance_field", table_name="process_data_provenance")
    op.drop_index("ix_process_data_provenance_process", table_name="process_data_provenance")
    op.drop_table("process_data_provenance")
    op.drop_index("ix_case_partes_party_entity_id", table_name="case_partes")
    op.drop_column("case_partes", "party_entity_id")
    op.drop_index("ux_party_entities_client_active", table_name="party_entities")
    op.drop_index("ux_party_entities_doc_hash_active", table_name="party_entities")
    op.drop_index("ix_party_entities_normalized_name", table_name="party_entities")
    op.drop_table("party_entities")
    op.drop_column("processes", "data_ajuizamento")
