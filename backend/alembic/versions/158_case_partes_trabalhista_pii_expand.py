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
    # Expand-only reversível: plaintext legado nunca foi removido nesta fase.
    op.execute("ALTER TABLE trabalhista_cases DROP COLUMN IF EXISTS cid_enc")
    op.execute("DROP INDEX IF EXISTS ux_case_partes_case_doc_hash_active")
    op.execute("ALTER TABLE case_partes DROP COLUMN IF EXISTS telefone_enc")
    op.execute("ALTER TABLE case_partes DROP COLUMN IF EXISTS email_enc")
    op.execute("ALTER TABLE case_partes DROP COLUMN IF EXISTS cpf_cnpj_hash")
    op.execute("ALTER TABLE case_partes DROP COLUMN IF EXISTS cpf_cnpj_enc")
