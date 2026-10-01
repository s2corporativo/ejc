"""Índices de FKs documentais do financeiro.

Revision ID: 167_finance_fk_indexes
Revises: 166_finance_governance
Create Date: 2026-09-30
"""
from alembic import op

revision = "167_finance_fk_indexes"
down_revision = "166_finance_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_commission_payment_batches_comprovante_doc",
        "commission_payment_batches",
        ["comprovante_doc_id"],
    )
    op.create_index(
        "ix_partner_withdrawals_comprovante_doc",
        "partner_withdrawals",
        ["comprovante_doc_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_partner_withdrawals_comprovante_doc",
        table_name="partner_withdrawals",
    )
    op.drop_index(
        "ix_commission_payment_batches_comprovante_doc",
        table_name="commission_payment_batches",
    )
