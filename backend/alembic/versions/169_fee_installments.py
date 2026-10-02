"""Parcelas financeiras dos contratos de honorários.

Revision ID: 169_fee_installments
Revises: 168_finance_ged_links
Create Date: 2026-10-02

Mantém:
- fees = recebível/honorário mestre;
- fee_installments = cronograma do contrato;
- fee_payments = fonte soberana de entrada de caixa.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "169_fee_installments"
down_revision = "168_finance_ged_links"
branch_labels = None
depends_on = None


fee_status = postgresql.ENUM(
    "pendente",
    "pago",
    "atrasado",
    "cancelado",
    name="feestatus",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "fee_installments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "fee_id",
            sa.String(length=36),
            sa.ForeignKey("fees.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "contract_document_id",
            sa.String(length=36),
            sa.ForeignKey("legal_docs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "client_id",
            sa.String(length=36),
            sa.ForeignKey("clients.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("installment_number", sa.Integer(), nullable=False),
        sa.Column("installment_count", sa.Integer(), nullable=False),
        sa.Column(
            "kind",
            sa.String(length=20),
            nullable=False,
            server_default="parcela",
        ),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            fee_status,
            nullable=False,
            server_default="pendente",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "amount > 0",
            name="ck_fee_installments_amount_positive",
        ),
        sa.CheckConstraint(
            "installment_number >= 1",
            name="ck_fee_installments_number_positive",
        ),
        sa.CheckConstraint(
            "installment_count >= 1",
            name="ck_fee_installments_count_positive",
        ),
        sa.CheckConstraint(
            "installment_number <= installment_count",
            name="ck_fee_installments_number_lte_count",
        ),
        sa.CheckConstraint(
            "kind IN ('entrada', 'parcela')",
            name="ck_fee_installments_kind",
        ),
        sa.UniqueConstraint(
            "contract_document_id",
            "installment_number",
            name="uq_fee_installments_contract_number",
        ),
    )

    op.create_index(
        "ix_fee_installments_fee_id",
        "fee_installments",
        ["fee_id"],
    )
    op.create_index(
        "ix_fee_installments_contract_document_id",
        "fee_installments",
        ["contract_document_id"],
    )
    op.create_index(
        "ix_fee_installments_client_due",
        "fee_installments",
        ["client_id", "due_date"],
    )
    op.create_index(
        "ix_fee_installments_status_due",
        "fee_installments",
        ["status", "due_date"],
    )

    # Compatibilidade: pagamentos históricos continuam sem parcela explícita.
    op.add_column(
        "fee_payments",
        sa.Column(
            "installment_id",
            sa.String(length=36),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_fee_payments_installment",
        "fee_payments",
        "fee_installments",
        ["installment_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_fee_payments_installment_id",
        "fee_payments",
        ["installment_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fee_payments_installment_id",
        table_name="fee_payments",
    )
    op.drop_constraint(
        "fk_fee_payments_installment",
        "fee_payments",
        type_="foreignkey",
    )
    op.drop_column("fee_payments", "installment_id")

    op.drop_index(
        "ix_fee_installments_status_due",
        table_name="fee_installments",
    )
    op.drop_index(
        "ix_fee_installments_client_due",
        table_name="fee_installments",
    )
    op.drop_index(
        "ix_fee_installments_contract_document_id",
        table_name="fee_installments",
    )
    op.drop_index(
        "ix_fee_installments_fee_id",
        table_name="fee_installments",
    )
    op.drop_table("fee_installments")
