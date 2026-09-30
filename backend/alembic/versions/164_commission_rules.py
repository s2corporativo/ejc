"""Regras configuráveis e snapshots de comissões.

Revision ID: 164_commission_rules
Revises: 163_process_provenance_party_identity
Create Date: 2026-09-30
"""
from alembic import op
import sqlalchemy as sa

revision = "164_commission_rules"
down_revision = "163_process_provenance_party_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "commission_rules",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("escopo", sa.String(length=20), nullable=False),
        sa.Column("area", sa.String(length=50), nullable=True),
        sa.Column("advogado_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("case_id", sa.String(length=36), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=True),
        sa.Column("percentual_advogado", sa.Numeric(5, 2), nullable=False),
        sa.Column("descontar_despesas", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("prioridade", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("vigencia_inicio", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column("vigencia_fim", sa.Date(), nullable=True),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("escopo IN ('padrao','area','advogado','caso')", name="ck_commission_rules_scope"),
        sa.CheckConstraint("percentual_advogado >= 0 AND percentual_advogado <= 100", name="ck_commission_rules_pct"),
        sa.CheckConstraint("vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio", name="ck_commission_rules_dates"),
    )
    op.create_index("ix_commission_rules_scope_active", "commission_rules", ["escopo", "ativo"])
    op.create_index("ix_commission_rules_area", "commission_rules", ["area"])
    op.create_index("ix_commission_rules_advogado", "commission_rules", ["advogado_id"])
    op.create_index("ix_commission_rules_case", "commission_rules", ["case_id"])

    op.add_column("case_receipt_allocations", sa.Column("commission_rule_id", sa.String(length=36), nullable=True))
    op.add_column("case_receipt_allocations", sa.Column("bruto_recebido", sa.Numeric(14, 2), nullable=True))
    op.add_column("case_receipt_allocations", sa.Column("despesas_deduzidas", sa.Numeric(14, 2), nullable=False, server_default="0"))
    op.add_column("case_receipt_allocations", sa.Column("base_liquida", sa.Numeric(14, 2), nullable=True))
    op.add_column("case_receipt_allocations", sa.Column("withdrawal_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_case_receipt_alloc_rule", "case_receipt_allocations", "commission_rules",
        ["commission_rule_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_case_receipt_alloc_rule", "case_receipt_allocations", ["commission_rule_id"])
    op.create_index("ix_case_receipt_alloc_withdrawal", "case_receipt_allocations", ["withdrawal_id"])

    op.execute("""
        UPDATE case_receipt_allocations a
           SET bruto_recebido = fp.valor,
               base_liquida = fp.valor,
               despesas_deduzidas = 0
          FROM fee_payments fp
         WHERE fp.id = a.fee_payment_id
           AND (a.bruto_recebido IS NULL OR a.base_liquida IS NULL)
    """)
    op.alter_column("case_receipt_allocations", "bruto_recebido", nullable=False)
    op.alter_column("case_receipt_allocations", "base_liquida", nullable=False)

    op.execute("""
        INSERT INTO commission_rules
            (id, nome, escopo, percentual_advogado, descontar_despesas, prioridade, ativo)
        VALUES
            ('commission-default-50', 'Regra padrão 50/50', 'padrao', 50.00, TRUE, 100, TRUE),
            ('commission-area-civil-0', 'Carteira civil — 100% escritório', 'area', 0.00, TRUE, 10, TRUE)
    """)
    op.execute("UPDATE commission_rules SET area='civil' WHERE id='commission-area-civil-0'")

    op.execute("""
        UPDATE case_receipt_allocations a
           SET withdrawal_id = pw.id
          FROM partner_withdrawals pw
         WHERE pw.deleted_at IS NULL
           AND pw.period_reference = ('case:' || left(a.fee_payment_id, 30))
           AND a.withdrawal_id IS NULL
    """)


def downgrade() -> None:
    op.drop_index("ix_case_receipt_alloc_withdrawal", table_name="case_receipt_allocations")
    op.drop_index("ix_case_receipt_alloc_rule", table_name="case_receipt_allocations")
    op.drop_constraint("fk_case_receipt_alloc_rule", "case_receipt_allocations", type_="foreignkey")
    op.drop_column("case_receipt_allocations", "withdrawal_id")
    op.drop_column("case_receipt_allocations", "base_liquida")
    op.drop_column("case_receipt_allocations", "despesas_deduzidas")
    op.drop_column("case_receipt_allocations", "bruto_recebido")
    op.drop_column("case_receipt_allocations", "commission_rule_id")
    op.drop_index("ix_commission_rules_case", table_name="commission_rules")
    op.drop_index("ix_commission_rules_advogado", table_name="commission_rules")
    op.drop_index("ix_commission_rules_area", table_name="commission_rules")
    op.drop_index("ix_commission_rules_scope_active", table_name="commission_rules")
    op.drop_table("commission_rules")
