"""158 — DB-03 Fase A: expand para PII cifrada em partes e CID trabalhista.

Expand-only. NÃO remove nem transforma automaticamente as colunas plaintext
legadas. O runtime novo passa a gravar somente ciphertext/hash e a ler legado
apenas quando ainda não existe ciphertext. O cutover físico fica para migration
posterior, condicionado a `legacy_plaintext_count=0` comprovado.

Revision ID: 158_case_partes_trabalhista_pii_expand
Revises: 157_ajuizamento_judicial
"""
from alembic import op

revision = "158_case_partes_trabalhista_pii_expand"
down_revision = "157_ajuizamento_judicial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE case_partes ADD COLUMN IF NOT EXISTS cpf_cnpj_enc text")
    op.execute("ALTER TABLE case_partes ADD COLUMN IF NOT EXISTS cpf_cnpj_hash varchar(64)")
    op.execute("ALTER TABLE case_partes ADD COLUMN IF NOT EXISTS email_enc text")
    op.execute("ALTER TABLE case_partes ADD COLUMN IF NOT EXISTS telefone_enc text")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_case_partes_case_doc_hash_active "
        "ON case_partes (case_id, cpf_cnpj_hash) "
        "WHERE cpf_cnpj_hash IS NOT NULL AND ativo = true"
    )
    op.execute("ALTER TABLE trabalhista_cases ADD COLUMN IF NOT EXISTS cid_enc text")


def downgrade() -> None:
    # Rollback físico só é seguro antes de o runtime novo receber PII. Como os
    # setters da Fase A limpam o plaintext legado, remover as colunas cifradas
    # depois de uso perderia dados. Falhamos fechado ANTES de qualquer DROP.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM case_partes
                WHERE cpf_cnpj_enc IS NOT NULL
                   OR cpf_cnpj_hash IS NOT NULL
                   OR email_enc IS NOT NULL
                   OR telefone_enc IS NOT NULL
            ) OR EXISTS (
                SELECT 1
                FROM trabalhista_cases
                WHERE cid_enc IS NOT NULL
            ) THEN
                RAISE EXCEPTION
                    'downgrade 158 bloqueado: existem valores cifrados; preserve os dados antes do rollback físico';
            END IF;
        END
        $$;
        """
    )
    op.execute("ALTER TABLE trabalhista_cases DROP COLUMN IF EXISTS cid_enc")
    op.execute("DROP INDEX IF EXISTS ux_case_partes_case_doc_hash_active")
    op.execute("ALTER TABLE case_partes DROP COLUMN IF EXISTS telefone_enc")
    op.execute("ALTER TABLE case_partes DROP COLUMN IF EXISTS email_enc")
    op.execute("ALTER TABLE case_partes DROP COLUMN IF EXISTS cpf_cnpj_hash")
    op.execute("ALTER TABLE case_partes DROP COLUMN IF EXISTS cpf_cnpj_enc")
