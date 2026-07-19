"""088 — refresh_tokens: janela de graça na detecção de reuso (corrida multi-aba)

Auditoria pré-go-live (item 1, ALTO): duas abas compartilham o cookie httpOnly
`ejc_refresh`; um refresh concorrente fazia a 2ª requisição chegar com o token
recém-revogado pela 1ª → a detecção de reuso revogava TODAS as sessões do
usuário (logout em massa em uso normal; retry de rede idem).

Novas colunas (preenchidas na rotação em routers/auth.py):
- revoked_at      — QUANDO o token foi revogado pela rotação;
- replaced_by_jti — jti do token que o substituiu (encadeia as rotações).

Reuso do token da ÚLTIMA rotação (replaced_by_jti aponta para token ainda
ativo) dentro da graça de 60s = corrida benigna → 401 simples, sem punição.
Reuso fora da graça, de token de rotação mais antiga ou revogado por punição
= replay → revoga todas as sessões + audit REFRESH_REUSE (comportamento
anterior preservado).

Tokens legados (revoked_at IS NULL) continuam com a punição total — nenhuma
migração de dados é necessária.

ADITIVO PURO e IDEMPOTENTE: ADD COLUMN IF NOT EXISTS (padrão das 086/087).

Revision ID: 088_refresh_token_graca_rotacao
Revises: 087_client_crm_lead_fields
Create Date: 2026-07-12
"""
from alembic import op

revision = "088_refresh_token_graca_rotacao"
down_revision = "087_client_crm_lead_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE refresh_tokens "
        "ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ NULL"
    )
    op.execute(
        "ALTER TABLE refresh_tokens "
        "ADD COLUMN IF NOT EXISTS replaced_by_jti VARCHAR(36) NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE refresh_tokens DROP COLUMN IF EXISTS replaced_by_jti")
    op.execute("ALTER TABLE refresh_tokens DROP COLUMN IF EXISTS revoked_at")
