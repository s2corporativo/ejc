"""Vínculos GED canônicos do financeiro.

Revision ID: 168_finance_ged_links
Revises: 167_finance_fk_indexes
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa

revision = "168_finance_ged_links"
down_revision = "167_finance_fk_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "office_expenses",
        sa.Column("comprovante_doc_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_office_expenses_comprovante_doc",
        "office_expenses",
        "documents",
        ["comprovante_doc_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_office_expenses_comprovante_doc",
        "office_expenses",
        ["comprovante_doc_id"],
    )

    op.add_column(
        "bank_analyses",
        sa.Column("document_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_bank_analyses_document",
        "bank_analyses",
        "documents",
        ["document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_bank_analyses_document", "bank_analyses", ["document_id"])

    # A coluna já existia, mas era VARCHAR solto. A auditoria pré-migration
    # confirmou zero referências órfãs em produção.
    op.create_foreign_key(
        "fk_fee_payments_comprovante_doc",
        "fee_payments",
        "documents",
        ["comprovante_doc_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_fee_payments_comprovante_doc",
        "fee_payments",
        ["comprovante_doc_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_fee_payments_comprovante_doc", table_name="fee_payments")
    op.drop_constraint(
        "fk_fee_payments_comprovante_doc",
        "fee_payments",
        type_="foreignkey",
    )

    op.drop_index("ix_bank_analyses_document", table_name="bank_analyses")
    op.drop_constraint(
        "fk_bank_analyses_document",
        "bank_analyses",
        type_="foreignkey",
    )
    op.drop_column("bank_analyses", "document_id")

    op.drop_index("ix_office_expenses_comprovante_doc", table_name="office_expenses")
    op.drop_constraint(
        "fk_office_expenses_comprovante_doc",
        "office_expenses",
        type_="foreignkey",
    )
    op.drop_column("office_expenses", "comprovante_doc_id")
