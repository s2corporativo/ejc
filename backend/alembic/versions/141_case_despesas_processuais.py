"""141 — Cria case_despesas (despesa processual lançada no caso).

Contexto (F3.2 / Issue #806): "lançar despesa por caso" não existia em
lugar nenhum. `office_expenses` (SQL bruto) é overhead do escritório,
restrito a superadmin/admin/socio/financeiro (`despesas.py::_req_fin`) —
categoria e RBAC incompatíveis com despesa PROCESSUAL, lançada por quem
trabalha o caso (advogado responsável) e existente para ser reembolsada
pelo cliente via honorário `custas_despesas` (FeeTipo já existe,
migration 097).

Mesmo padrão de `time_entries` (migration 003): lançamento cru com
`fee_id` nulo até uma consolidação explícita gerar o Fee — nunca fatura
sozinho.

downgrade: dropa a tabela. Nenhuma outra tabela referencia
`case_despesas` (FK só sai daqui, nunca entra).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "141_case_despesas_processuais"
down_revision = "138_consolida_fontes_ingestao"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_despesas",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("data", sa.Date, nullable=False),
        sa.Column("valor", sa.Numeric(14, 2), nullable=False),
        sa.Column("descricao", sa.String(500), nullable=False),
        sa.Column("categoria", sa.String(30), nullable=False, server_default="outro"),
        sa.Column("fee_id", sa.String(36), sa.ForeignKey("fees.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_case_despesas_case_id", "case_despesas", ["case_id"])
    op.create_index("ix_case_despesas_user_id", "case_despesas", ["user_id"])
    op.create_index("ix_case_despesas_fee_id", "case_despesas", ["fee_id"])


def downgrade() -> None:
    op.drop_index("ix_case_despesas_fee_id", table_name="case_despesas")
    op.drop_index("ix_case_despesas_user_id", table_name="case_despesas")
    op.drop_index("ix_case_despesas_case_id", table_name="case_despesas")
    op.drop_table("case_despesas")
