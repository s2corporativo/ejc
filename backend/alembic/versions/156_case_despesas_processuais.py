"""156 — despesas processuais vinculadas ao caso.

Separa custo do processo (reembolsável ao cliente) de `office_expenses`
(overhead do escritório). O faturamento continua explícito: `fee_id` nasce
NULL e só é preenchido quando um Fee `custas_despesas` é gerado.

Migration aditiva. Nenhuma tabela existente é alterada ou removida.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "156_case_despesas_processuais"
down_revision = "155_indices_listagem_espinha"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_despesas",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "case_id",
            sa.String(36),
            sa.ForeignKey("cases.id"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("valor", sa.Numeric(14, 2), nullable=False),
        sa.Column("descricao", sa.String(500), nullable=False),
        sa.Column(
            "categoria",
            sa.String(30),
            nullable=False,
            server_default="outro",
        ),
        sa.Column(
            "fee_id",
            sa.String(36),
            sa.ForeignKey("fees.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
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
