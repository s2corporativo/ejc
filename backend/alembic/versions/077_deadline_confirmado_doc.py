"""077_deadline_confirmado_doc — Gap C (#83): prazo rascunho extraído por IA

Fundação para "prazo extraído por IA, a confirmar":
- confirmado (Boolean NOT NULL, default TRUE): prazos existentes/manuais nascem
  confirmados; só os extraídos por IA nascem false ("a confirmar"). É informativo/UX
  — NÃO altera a lógica de alerta (o prazo já dispara 7d/3d/1d normalmente).
- origem_documento_id (FK documents.id, nullable): rastreabilidade do documento
  (GED) que originou o prazo. O valor origem='importacao_ia' fica a cargo do
  backend (origem é String, sem constraint nova).

Ordem: ADD COLUMN com DEFAULT true faz o backfill dos registros existentes de forma
atômica no próprio ADD; a coluna já entra NOT NULL sem passo separado.
Idempotente (IF NOT EXISTS) para deploy limpo + produção, seguindo o padrão das
migrations de deadlines (057).

Revision ID: 077_deadline_confirmado_doc
Revises: 076_fk_hot_path_indexes
"""
from alembic import op

revision = "077_deadline_confirmado_doc"
down_revision = "076_fk_hot_path_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # DEFAULT true no ADD COLUMN preenche as linhas existentes (backfill implícito),
    # então a coluna já pode nascer NOT NULL numa única instrução.
    op.execute(
        "ALTER TABLE deadlines "
        "ADD COLUMN IF NOT EXISTS confirmado boolean NOT NULL DEFAULT true"
    )
    op.execute(
        "ALTER TABLE deadlines "
        "ADD COLUMN IF NOT EXISTS origem_documento_id varchar(36) "
        "REFERENCES documents(id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_deadlines_origem_documento_id "
        "ON deadlines(origem_documento_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_deadlines_origem_documento_id")
    op.execute("ALTER TABLE deadlines DROP COLUMN IF EXISTS origem_documento_id")
    op.execute("ALTER TABLE deadlines DROP COLUMN IF EXISTS confirmado")
