"""DJEN: unicidade por advogado e evidência oficial da comunicação.

Auditoria do módulo DJEN (2026-10):
  • `comunicacao_id_externo` era UNIQUE global — a mesma comunicação destinada
    a dois advogados do escritório só era entregue ao primeiro que a capturasse.
    Passa a ser única por (comunicacao_id_externo, advogado_id).
  • Persiste a evidência oficial: link do PDF, órgão julgador e texto íntegro
    (sem tags), antes truncado em 2000 caracteres.

Aditiva e reversível; o downgrade recusa-se a reintroduzir a unicidade global
se já houver comunicação replicada entre advogados (evita perda de dado).

Revision ID: 169_djen_multi_advogado
Revises: 168_finance_ged_links
Create Date: 2026-10-02
"""
from alembic import op

revision = "169_djen_multi_advogado"
down_revision = "168_finance_ged_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE djen_comunicacoes ADD COLUMN IF NOT EXISTS link_oficial TEXT")
    op.execute("ALTER TABLE djen_comunicacoes ADD COLUMN IF NOT EXISTS orgao VARCHAR(255)")
    op.execute("ALTER TABLE djen_comunicacoes ADD COLUMN IF NOT EXISTS texto_integral TEXT")

    # Remove a unicidade global (índice único e/ou constraint, conforme o histórico).
    op.execute(
        "ALTER TABLE djen_comunicacoes "
        "DROP CONSTRAINT IF EXISTS djen_comunicacoes_comunicacao_id_externo_key"
    )
    op.execute("DROP INDEX IF EXISTS ix_djen_comunicacoes_comunicacao_id_externo")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_djen_comunicacoes_comunicacao_id_externo "
        "ON djen_comunicacoes (comunicacao_id_externo)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_djen_comunicacao_externo_advogado "
        "ON djen_comunicacoes (comunicacao_id_externo, advogado_id)"
    )


def downgrade() -> None:
    conn = op.get_bind()
    repetidas = conn.exec_driver_sql(
        "SELECT count(*) FROM (SELECT 1 FROM djen_comunicacoes "
        "GROUP BY comunicacao_id_externo HAVING count(*) > 1) t"
    ).scalar()
    if repetidas:
        raise RuntimeError(
            "downgrade 169 recusado: existem comunicações DJEN replicadas entre "
            "advogados; reintroduzir a unicidade global descartaria dados."
        )
    op.execute("DROP INDEX IF EXISTS uq_djen_comunicacao_externo_advogado")
    op.execute("DROP INDEX IF EXISTS ix_djen_comunicacoes_comunicacao_id_externo")
    op.execute(
        "CREATE UNIQUE INDEX ix_djen_comunicacoes_comunicacao_id_externo "
        "ON djen_comunicacoes (comunicacao_id_externo)"
    )
    op.execute("ALTER TABLE djen_comunicacoes DROP COLUMN IF EXISTS texto_integral")
    op.execute("ALTER TABLE djen_comunicacoes DROP COLUMN IF EXISTS orgao")
    op.execute("ALTER TABLE djen_comunicacoes DROP COLUMN IF EXISTS link_oficial")
