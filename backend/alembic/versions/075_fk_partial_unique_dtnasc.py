"""075 — Pente fino do banco: FK ai_logs, UNIQUE parcial (soft-delete) e tipo de data.

Corrige três achados da auditoria de banco, todos reversíveis:

1. FK faltando: `ai_logs.case_id` ganha FK -> cases.id ON DELETE SET NULL
   (antes era String solto sem integridade referencial). Órfãos são zerados
   ANTES do ADD CONSTRAINT, senão o Postgres recusa a constraint.

2. UNIQUE x SOFT-DELETE: `clients.cpf`, `clients.cnpj`, `users.email` e
   `cases.numero_interno` tinham UNIQUE "cheio", impedindo recadastro após um
   soft-delete (deleted_at preenchido). Substituídos por ÍNDICE ÚNICO PARCIAL
   `WHERE deleted_at IS NULL`: unicidade só entre registros ATIVOS. Como o
   UNIQUE cheio já era imposto (migrations 001/011/058) não há duplicatas
   ativas — a criação do índice parcial não falha com dados existentes.

3. TIPO: `clients.data_nascimento` de String(10) -> Date, tratando linhas
   vazias/malformadas (viram NULL).

Nota: FKs de isolamento RAG/api_keys (`knowledge_docs.client_id/case_id`,
`api_keys.client_id`) NÃO entram aqui — `client_id` do RAG é um identificador
de ESCOPO (nem sempre um cliente formal; o isolamento é imposto na camada de
serviço), então uma FK estrita rejeitaria escopos válidos. Fica como
recomendação (exige alinhar seeds/testes de escopo antes).

Revision ID: 075_fk_partial_unique_dtnasc
Revises: 074_remove_licitacao_admin_tipo
"""
from alembic import op
import sqlalchemy as sa

revision = "075_fk_partial_unique_dtnasc"
down_revision = "074_remove_licitacao_admin_tipo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. ai_logs.case_id → FK cases.id ON DELETE SET NULL ────────────────────
    op.execute(
        "UPDATE ai_logs SET case_id = NULL "
        "WHERE case_id IS NOT NULL AND case_id NOT IN (SELECT id FROM cases)"
    )
    op.create_foreign_key(
        "fk_ai_logs_case_id_cases", "ai_logs", "cases",
        ["case_id"], ["id"], ondelete="SET NULL",
    )

    # ── 2. UNIQUE cheio → ÍNDICE ÚNICO PARCIAL (WHERE deleted_at IS NULL) ───────
    # clients.cpf / clients.cnpj (constraints da migration 011)
    op.execute("ALTER TABLE clients DROP CONSTRAINT IF EXISTS uq_clients_cpf")
    op.execute("ALTER TABLE clients DROP CONSTRAINT IF EXISTS uq_clients_cnpj")
    op.create_index(
        "uq_clients_cpf_active", "clients", ["cpf"],
        unique=True, postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_clients_cnpj_active", "clients", ["cnpj"],
        unique=True, postgresql_where=sa.text("deleted_at IS NULL"),
    )
    # users.email (constraint users_email_key da 001 + índice uq_users_email da 058)
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_email_key")
    op.execute("DROP INDEX IF EXISTS uq_users_email")
    op.create_index(
        "uq_users_email_active", "users", ["email"],
        unique=True, postgresql_where=sa.text("deleted_at IS NULL"),
    )
    # cases.numero_interno (constraint inline da 001: cases_numero_interno_key)
    op.execute("ALTER TABLE cases DROP CONSTRAINT IF EXISTS cases_numero_interno_key")
    op.create_index(
        "uq_cases_numero_interno_active", "cases", ["numero_interno"],
        unique=True, postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ── 3. clients.data_nascimento String(10) → Date ───────────────────────────
    op.execute(
        r"""
        ALTER TABLE clients
        ALTER COLUMN data_nascimento TYPE date
        USING CASE
            WHEN data_nascimento IS NULL OR btrim(data_nascimento) = '' THEN NULL
            WHEN btrim(data_nascimento) ~ '^\d{4}-\d{2}-\d{2}$'
                THEN to_date(btrim(data_nascimento), 'YYYY-MM-DD')
            ELSE NULL
        END
        """
    )


def downgrade() -> None:
    # ── 3. data_nascimento Date → String(10) ───────────────────────────────────
    op.execute(
        """
        ALTER TABLE clients
        ALTER COLUMN data_nascimento TYPE varchar(10)
        USING CASE
            WHEN data_nascimento IS NULL THEN NULL
            ELSE to_char(data_nascimento, 'YYYY-MM-DD')
        END
        """
    )

    # ── 2. índices parciais → UNIQUE original ──────────────────────────────────
    op.drop_index("uq_cases_numero_interno_active", table_name="cases")
    op.create_unique_constraint("cases_numero_interno_key", "cases", ["numero_interno"])

    op.drop_index("uq_users_email_active", table_name="users")
    op.create_unique_constraint("users_email_key", "users", ["email"])
    # restaura o índice único idempotente da migration 058
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email ON users(email)")

    op.drop_index("uq_clients_cnpj_active", table_name="clients")
    op.drop_index("uq_clients_cpf_active", table_name="clients")
    op.create_unique_constraint("uq_clients_cnpj", "clients", ["cnpj"])
    op.create_unique_constraint("uq_clients_cpf", "clients", ["cpf"])

    # ── 1. reverte FK ai_logs.case_id ──────────────────────────────────────────
    op.drop_constraint("fk_ai_logs_case_id_cases", "ai_logs", type_="foreignkey")
