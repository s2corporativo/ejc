"""dedup cases columns: remove EN duplicates orfas (case_value, opposing_party, opposing_party_document)

Colunas duplicadas PT/EN em cases. Validado em 20/06/2026:
  - 100% NULL (0 de 12 linhas)
  - 0 referencias em codigo/ORM (grep /app/app -> NENHUMA_REFERENCIA)
Fonte da verdade (PT, preservada): valor_causa, parte_contraria, case_partes.
Reversivel: downgrade re-adiciona as colunas (eram nulas).

Revision ID: 047_dedup_cases
Revises: 046_wiki
"""
from alembic import op

revision = "047_dedup_cases"
down_revision = "046_wiki"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS case_value")
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS opposing_party")
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS opposing_party_document")


def downgrade():
    op.execute("ALTER TABLE cases ADD COLUMN IF NOT EXISTS case_value numeric")
    op.execute("ALTER TABLE cases ADD COLUMN IF NOT EXISTS opposing_party varchar")
    op.execute("ALTER TABLE cases ADD COLUMN IF NOT EXISTS opposing_party_document varchar")
