"""056_processes_is_principal — alinha banco↔código (A1, auditoria 2026-06-30)

O código (services/processo_service.py, routers/cases.py, schemas/case.py) lê e
grava `processes.is_principal`, mas NENHUMA migração criava a coluna — a 048 cria
`processes` sem ela. Em produção a coluna foi adicionada por ALTER manual fora do
Alembic (Fase 1), logo um deploy limpo / disaster recovery quebraria GET /cases/{id}
e o PATCH de número de processo (UndefinedColumn).

Esta migração torna o schema reproduzível. Totalmente IDEMPOTENTE:
- ADD COLUMN IF NOT EXISTS  → no-op onde já existe (produção).
- Backfill marca 1 principal por caso APENAS onde nenhum existe (guard NOT IN).
- CREATE UNIQUE INDEX IF NOT EXISTS → mesmo nome usado no ALTER manual.

Revision ID: 056_processes_is_principal
Revises: 055_rag_isolation
"""
from alembic import op

revision = "056_processes_is_principal"
down_revision = "055_rag_isolation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Coluna (no-op em produção, que já tem via ALTER manual)
    op.execute(
        "ALTER TABLE processes "
        "ADD COLUMN IF NOT EXISTS is_principal boolean NOT NULL DEFAULT false"
    )

    # 2. Backfill seguro: para cada caso SEM principal, marca o processo mais
    #    antigo (não-deletado) como principal. Idempotente pelo guard NOT IN.
    op.execute("""
        UPDATE processes
        SET is_principal = TRUE
        WHERE id IN (
            SELECT DISTINCT ON (case_id) id
            FROM processes
            WHERE deleted_at IS NULL
            ORDER BY case_id, created_at ASC, id ASC
        )
        AND case_id NOT IN (
            SELECT case_id FROM processes
            WHERE is_principal = TRUE AND deleted_at IS NULL
        )
    """)

    # 3. Unicidade: no máximo 1 principal ativo por caso (mesmo nome do ALTER manual)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_processes_principal_per_case "
        "ON processes(case_id) WHERE is_principal = TRUE AND deleted_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_processes_principal_per_case")
    op.execute("ALTER TABLE processes DROP COLUMN IF EXISTS is_principal")
