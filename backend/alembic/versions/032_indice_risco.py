"""indice_risco — histórico e colunas em cases

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-06-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "d2e3f4a5b6c7"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade():
    # Adicionar colunas de risco calculado em cases
    conn = op.get_bind()
    existing = [
        row[0]
        for row in conn.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='cases' AND column_name IN "
                "('indice_risco','risco_nivel','risco_fatores','risco_atualizado_em')"
            )
        )
    ]

    if "indice_risco" not in existing:
        op.add_column("cases", sa.Column("indice_risco", sa.Integer, server_default="0"))
    if "risco_nivel" not in existing:
        op.add_column("cases", sa.Column("risco_nivel", sa.String(10), server_default="baixo"))
    if "risco_fatores" not in existing:
        op.add_column("cases", sa.Column("risco_fatores", JSONB, server_default="{}"))
    if "risco_atualizado_em" not in existing:
        op.add_column("cases", sa.Column("risco_atualizado_em", sa.DateTime(timezone=True)))

    # Tabela de histórico
    op.create_table(
        "indice_risco_historico",
        sa.Column("id", sa.String, primary_key=True, server_default=sa.text("gen_random_uuid()::text")),
        sa.Column("case_id", sa.String, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("indice", sa.Integer, nullable=False),
        sa.Column("nivel", sa.String(10), nullable=False),
        sa.Column("fatores", JSONB),
        sa.Column("calculado_por", sa.String(20), server_default="sistema"),
        sa.Column("observacao", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_irh_case_id", "indice_risco_historico", ["case_id"])
    op.create_index("ix_irh_created", "indice_risco_historico", ["case_id", "created_at"])


def downgrade():
    # DDL idempotente (IF EXISTS) em vez de try/except: pass.
    # Motivo: o EJC roda o downgrade em UMA única transação (alembic/env.py NÃO usa
    # transaction_per_migration). Um DROP que falha (objeto ausente) ABORTA a
    # transação inteira; o `except: pass` engolia o erro Python mas NÃO desfazia o
    # abort SQL — a próxima instrução (inclusive o UPDATE alembic_version) quebrava
    # com InFailedSqlTransaction e travava o rollback profundo (ex.: 036→033→032,
    # em que a 036 recria procuracoes.case_id sem o índice e o drop_index da 033
    # falha). Com IF EXISTS nenhuma exceção é lançada e a transação nunca aborta.
    # NOTA (regra do repo): só o downgrade() muda — o upgrade() já aplicado em
    # produção fica INTOCADO; esta alteração afeta apenas reversões futuras.
    # DROP TABLE remove automaticamente os índices ix_irh_case_id/ix_irh_created.
    op.execute("DROP TABLE IF EXISTS indice_risco_historico")
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS indice_risco")
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS risco_nivel")
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS risco_fatores")
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS risco_atualizado_em")
