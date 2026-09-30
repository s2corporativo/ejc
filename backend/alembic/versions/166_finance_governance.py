"""Governança financeira: fechamento, alçada e conciliação.

Revision ID: 166_finance_governance
Revises: 165_commission_operations
Create Date: 2026-09-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "166_finance_governance"
down_revision = "165_commission_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "finance_month_closings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("competencia", sa.String(length=7), nullable=False, unique=True),
        sa.Column("snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("closed_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("competencia ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'", name="ck_fin_close_comp"),
    )
    op.create_index("ix_finance_month_closings_closed", "finance_month_closings", ["closed_at"])

    op.create_table(
        "finance_policy_settings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("double_approval_threshold", sa.Numeric(14,2), nullable=False, server_default="10000"),
        sa.Column("updated_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("double_approval_threshold >= 0", name="ck_fin_policy_threshold"),
    )
    op.execute("""
        INSERT INTO finance_policy_settings (id,double_approval_threshold)
        VALUES ('default',10000.00)
        ON CONFLICT (id) DO NOTHING
    """)

    op.create_table(
        "finance_payment_approvals",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("entity_type", sa.String(length=30), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("amount", sa.Numeric(14,2), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pendente"),
        sa.Column("requested_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("reason", sa.Text()),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint("entity_type IN ('office_expense','case_expense','commission_batch','profit_distribution')", name="ck_fin_approval_type"),
        sa.CheckConstraint("status IN ('pendente','aprovado','rejeitado','consumido')", name="ck_fin_approval_status"),
        sa.CheckConstraint("amount >= 0", name="ck_fin_approval_amount"),
    )
    op.create_index("ix_fin_approval_entity", "finance_payment_approvals", ["entity_type","entity_id","status"])

    op.create_table(
        "finance_reconciliation_matches",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("bank_transaction_id", sa.String(length=36), nullable=False),
        sa.Column("target_type", sa.String(length=30), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("confidence", sa.Numeric(5,4), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="sugerido"),
        sa.Column("reason", sa.Text()),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("confirmed_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("target_type IN ('fee_payment','office_expense','commission_batch')", name="ck_fin_recon_target"),
        sa.CheckConstraint("status IN ('sugerido','confirmado','rejeitado')", name="ck_fin_recon_status"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_fin_recon_conf"),
        sa.UniqueConstraint("bank_transaction_id", "target_type", "target_id", name="uq_fin_recon_candidate"),
    )
    op.create_index("ix_fin_recon_bank_tx", "finance_reconciliation_matches", ["bank_transaction_id","status"])


def downgrade() -> None:
    op.drop_index("ix_fin_recon_bank_tx", table_name="finance_reconciliation_matches")
    op.drop_table("finance_reconciliation_matches")
    op.drop_index("ix_fin_approval_entity", table_name="finance_payment_approvals")
    op.drop_table("finance_payment_approvals")
    op.drop_table("finance_policy_settings")
    op.drop_index("ix_finance_month_closings_closed", table_name="finance_month_closings")
    op.drop_table("finance_month_closings")
