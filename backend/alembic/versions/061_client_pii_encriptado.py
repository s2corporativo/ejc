"""061_client_pii_encriptado: colunas p/ cpf/cnpj cifrados (LGPD, Bloco 6a)

ADITIVO PURO: só ADD COLUMN, sem tocar nas colunas cpf/cnpj existentes (texto
puro) e sem migrar/apagar nenhum dado. Os clientes já cadastrados continuam
com cpf/cnpj em texto puro até o backfill manual ser executado (ver
scripts/backfill_pii_encryption.py — não roda automaticamente, exige backup
e confirmação explícita, é um passo separado e deliberado desta migration).

Colunas novas:
- cpf_enc / cnpj_enc: ciphertext (Fernet) — não determinístico, seguro em
  repouso, não indexável.
- cpf_hash / cnpj_hash: HMAC-SHA256 (índice cego) — determinístico, usado p/
  dedup/conflito de interesses/busca EXATA sem expor o valor em claro.

Revision ID: 061_client_pii_encriptado
Revises: 060_client_anonimizacao
"""
from alembic import op

revision = "061_client_pii_encriptado"
down_revision = "060_client_anonimizacao"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS cpf_enc text")
    op.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS cnpj_enc text")
    op.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS cpf_hash varchar(64)")
    op.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS cnpj_hash varchar(64)")
    # Únicos parciais (permitem múltiplos NULL — clientes ainda não migrados
    # ou PJ sem CPF/PF sem CNPJ não colidem).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_clients_cpf_hash "
        "ON clients (cpf_hash) WHERE cpf_hash IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_clients_cnpj_hash "
        "ON clients (cnpj_hash) WHERE cnpj_hash IS NOT NULL"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ux_clients_cnpj_hash")
    op.execute("DROP INDEX IF EXISTS ux_clients_cpf_hash")
    op.execute("ALTER TABLE clients DROP COLUMN IF EXISTS cnpj_hash")
    op.execute("ALTER TABLE clients DROP COLUMN IF EXISTS cpf_hash")
    op.execute("ALTER TABLE clients DROP COLUMN IF EXISTS cnpj_enc")
    op.execute("ALTER TABLE clients DROP COLUMN IF EXISTS cpf_enc")
