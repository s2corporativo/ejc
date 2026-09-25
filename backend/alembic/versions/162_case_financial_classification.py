"""Classificação econômica do caso e rateio de recebimentos.

Revision ID: 162_case_financial_classification
Revises: 161_fee_estornos
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa

revision = "162_case_financial_classification"
down_revision = "161_fee_estornos"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("cases", sa.Column("classificacao_financeira", sa.String(length=20), nullable=False, server_default="normal"))
    op.add_column("cases", sa.Column("valor_pleiteado", sa.Numeric(14, 2), nullable=True))
    op.add_column("cases", sa.Column("pendente_sucumbencia", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("cases", sa.Column("pendente_exito", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_check_constraint(
        "ck_cases_classificacao_financeira", "cases",
        "classificacao_financeira IN ('normal','pro_bono','causa_propria')",
    )
    op.create_table(
        "case_receipt_allocations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("case_id", sa.String(length=36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fee_payment_id", sa.String(length=36), sa.ForeignKey("fee_payments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("advogado_responsavel_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("percentual_advogado", sa.Numeric(5, 2), nullable=False),
        sa.Column("valor_advogado", sa.Numeric(14, 2), nullable=False),
        sa.Column("valor_escritorio", sa.Numeric(14, 2), nullable=False),
        sa.Column("regra", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("fee_payment_id", name="uq_case_receipt_alloc_payment"),
    )
    op.create_index("ix_case_receipt_alloc_case", "case_receipt_allocations", ["case_id"])
    op.create_index("ix_case_receipt_alloc_payment", "case_receipt_allocations", ["fee_payment_id"])
    op.create_index("ix_case_receipt_alloc_advogado", "case_receipt_allocations", ["advogado_responsavel_id"])

def downgrade() -> None:
    op.drop_index("ix_case_receipt_alloc_advogado", table_name="case_receipt_allocations")
    op.drop_index("ix_case_receipt_alloc_payment", table_name="case_receipt_allocations")
    op.drop_index("ix_case_receipt_alloc_case", table_name="case_receipt_allocations")
    op.drop_table("case_receipt_allocations")
    op.drop_constraint("ck_cases_classificacao_financeira", "cases", type_="check")
    op.drop_column("cases", "pendente_exito")
    op.drop_column("cases", "pendente_sucumbencia")
    op.drop_column("cases", "valor_pleiteado")
    op.drop_column("cases", "classificacao_financeira")
