"""Fechamento operacional de comissões: ajustes, lotes e competência.

Revision ID: 165_commission_operations
Revises: 164_commission_rules
Create Date: 2026-09-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "165_commission_operations"
down_revision = "164_commission_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "commission_adjustments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "allocation_id",
            sa.String(length=36),
            sa.ForeignKey("case_receipt_allocations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "fee_estorno_id",
            sa.String(length=36),
            sa.ForeignKey("fee_estornos.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("valor_advogado", sa.Numeric(14, 2), nullable=False),
        sa.Column("valor_escritorio", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "applied_value",
            sa.Numeric(14, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.Column(
            "created_by",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "source_type IN ('estorno','ajuste')",
            name="ck_commission_adjustments_source",
        ),
        sa.CheckConstraint(
            "valor_advogado <> 0 OR valor_escritorio <> 0",
            name="ck_commission_adjustments_nonzero",
        ),
    )
    op.create_index(
        "ix_commission_adjustments_allocation",
        "commission_adjustments",
        ["allocation_id", "created_at"],
    )
    op.create_index(
        "ix_commission_adjustments_estorno",
        "commission_adjustments",
        ["fee_estorno_id"],
        unique=True,
        postgresql_where=sa.text("fee_estorno_id IS NOT NULL"),
    )

    op.create_table(
        "commission_payment_batches",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("competencia", sa.String(length=7), nullable=False),
        sa.Column("payment_method", sa.String(length=30), nullable=False),
        sa.Column("payment_reference", sa.String(length=120), nullable=True),
        sa.Column(
            "comprovante_doc_id",
            sa.String(length=36),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column("total_pago", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "paid_by",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "competencia ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'",
            name="ck_commission_batches_competencia",
        ),
        sa.CheckConstraint(
            "total_pago >= 0",
            name="ck_commission_batches_total",
        ),
    )
    op.create_index(
        "ix_commission_batches_competencia",
        "commission_payment_batches",
        ["competencia", "paid_at"],
    )

    op.create_table(
        "commission_payment_batch_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "batch_id",
            sa.String(length=36),
            sa.ForeignKey("commission_payment_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "partner_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("withdrawal_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("adjustment_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("valor_retiradas", sa.Numeric(14, 2), nullable=False),
        sa.Column("valor_ajustes", sa.Numeric(14, 2), nullable=False),
        sa.Column("valor_pago", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("valor_pago >= 0", name="ck_commission_batch_items_paid"),
    )
    op.create_index(
        "ix_commission_batch_items_batch",
        "commission_payment_batch_items",
        ["batch_id", "partner_id"],
    )

    op.create_table(
        "commission_month_closings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("competencia", sa.String(length=7), nullable=False, unique=True),
        sa.Column(
            "snapshot_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "closed_by",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "competencia ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'",
            name="ck_commission_closings_competencia",
        ),
    )
    op.create_index(
        "ix_commission_closings_closed",
        "commission_month_closings",
        ["closed_at"],
    )

    op.add_column(
        "partner_withdrawals",
        sa.Column("payment_method", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "partner_withdrawals",
        sa.Column("payment_reference", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "partner_withdrawals",
        sa.Column(
            "comprovante_doc_id",
            sa.String(length=36),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "partner_withdrawals",
        sa.Column(
            "paid_by",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "partner_withdrawals",
        sa.Column(
            "payment_batch_id",
            sa.String(length=36),
            sa.ForeignKey("commission_payment_batches.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_partner_withdrawals_batch",
        "partner_withdrawals",
        ["payment_batch_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_partner_withdrawals_batch", table_name="partner_withdrawals")
    op.drop_column("partner_withdrawals", "payment_batch_id")
    op.drop_column("partner_withdrawals", "paid_by")
    op.drop_column("partner_withdrawals", "comprovante_doc_id")
    op.drop_column("partner_withdrawals", "payment_reference")
    op.drop_column("partner_withdrawals", "payment_method")

    op.drop_index("ix_commission_closings_closed", table_name="commission_month_closings")
    op.drop_table("commission_month_closings")
    op.drop_index("ix_commission_batch_items_batch", table_name="commission_payment_batch_items")
    op.drop_table("commission_payment_batch_items")
    op.drop_index("ix_commission_batches_competencia", table_name="commission_payment_batches")
    op.drop_table("commission_payment_batches")
    op.drop_index("ix_commission_adjustments_estorno", table_name="commission_adjustments")
    op.drop_index("ix_commission_adjustments_allocation", table_name="commission_adjustments")
    op.drop_table("commission_adjustments")
