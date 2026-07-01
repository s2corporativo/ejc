"""processes: entidade Processo independente do Caso (1 Caso : N Processos)

Resolve a violacao estrutural Caso=Processo (auto-FK linked_judicial_case_id, 1:1).
ADITIVO: cria a tabela e faz backfill dos casos que ja tem numero de processo.
NAO altera cases nem conversao_caso (transicao). Reversivel (downgrade dropa).

Revision ID: 048_processes
Revises: 047_dedup_cases
"""
from alembic import op

revision = "048_processes"
down_revision = "047_dedup_cases"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS processes (
            id varchar(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            case_id varchar(36) NOT NULL REFERENCES cases(id),
            numero_cnj varchar(30),
            instancia varchar(20),
            tribunal varchar(160),
            comarca varchar(160),
            vara varchar(160),
            classe varchar(160),
            fase varchar(40),
            tipo varchar(30) NOT NULL DEFAULT 'judicial',
            processo_principal_id varchar(36) REFERENCES processes(id),
            valor_causa numeric,
            status varchar(30) NOT NULL DEFAULT 'ativo',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            deleted_at timestamptz
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_processes_case_id ON processes(case_id)")
    # Backfill idempotente: cada caso com numero_processo vira 1 processo judicial.
    op.execute("""
        INSERT INTO processes (id, case_id, numero_cnj, tribunal, comarca, vara, tipo, valor_causa, status, created_at, updated_at)
        SELECT gen_random_uuid()::text, c.id, NULLIF(c.numero_processo, ''), c.tribunal, c.comarca, c.vara,
               'judicial', c.valor_causa, 'ativo', now(), now()
        FROM cases c
        WHERE c.deleted_at IS NULL
          AND c.numero_processo IS NOT NULL AND c.numero_processo <> ''
          AND NOT EXISTS (SELECT 1 FROM processes p WHERE p.case_id = c.id)
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS processes CASCADE")
