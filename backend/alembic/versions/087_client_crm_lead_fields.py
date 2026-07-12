"""087 — campos de funil de leads em clients (CRM)

Correção de auditoria do funil de leads (CRMLeads/CentralRelacionamento): o
model Client passou a declarar `etapa_funil`, `origem_lead` e `area_interesse`
na seção CRM, mas as colunas não existiam no banco — drift model↔schema.

Colunas VARCHAR nullable com validação de domínio na aplicação (etapa restrita
a ETAPAS_FUNIL no schema Pydantic) — mesmo trade-off das migrations 073/084/085
(evita ENUM nativo por valor de coluna de board). Índice não-único
ix_clients_etapa_funil suporta a listagem do board por etapa.

Nota: o comentário no model cita "migration 086", mas 086 já era
086_totp_secret_cifrado (head real da cadeia) — por isso esta é a 087.

ADITIVO PURO e IDEMPOTENTE: ADD COLUMN IF NOT EXISTS / CREATE INDEX IF NOT
EXISTS.

Revision ID: 087_client_crm_lead_fields
Revises: 086_totp_secret_cifrado
Create Date: 2026-07-12
"""
from alembic import op

revision = "087_client_crm_lead_fields"
down_revision = "086_totp_secret_cifrado"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS etapa_funil VARCHAR(20)"
    )
    op.execute(
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS origem_lead VARCHAR(50)"
    )
    op.execute(
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS area_interesse VARCHAR(100)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clients_etapa_funil "
        "ON clients (etapa_funil)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_clients_etapa_funil")
    op.execute("ALTER TABLE clients DROP COLUMN IF EXISTS area_interesse")
    op.execute("ALTER TABLE clients DROP COLUMN IF EXISTS origem_lead")
    op.execute("ALTER TABLE clients DROP COLUMN IF EXISTS etapa_funil")
