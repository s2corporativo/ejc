"""115 — campo proxima_acao obrigatório para casos ativos (G1).

Revision ID: 115_case_proxima_acao
Revises: 114_consolidar_v4
Create Date: 2026-07-23

Adiciona proxima_acao (Text) e proxima_acao_prazo (timestamptz) ao caso.
Campos nullable — a obrigatoriedade é validada na camada de aplicação
(router) apenas para casos com status triagem/ativo/suspenso/acordo.
Casos encerrados/arquivados não precisam de próxima ação.
"""
from alembic import op
import sqlalchemy as sa

revision = "115_case_proxima_acao"
down_revision = "114_consolidar_v4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("proxima_acao", sa.Text(), nullable=True))
    op.add_column("cases", sa.Column(
        "proxima_acao_prazo",
        sa.DateTime(timezone=True),
        nullable=True,
    ))
    # Índice parcial: casos ATIVOS com próxima ação pendente (dashboard query).
    op.execute(
        r"""
        CREATE INDEX IF NOT EXISTS ix_cases_proxima_acao_pendente
        ON cases (proxima_acao_prazo)
        WHERE deleted_at IS NULL
          AND status IN ('triagem', 'ativo', 'suspenso', 'acordo')
          AND proxima_acao IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_cases_proxima_acao_pendente", table_name="cases")
    op.drop_column("cases", "proxima_acao_prazo")
    op.drop_column("cases", "proxima_acao")
