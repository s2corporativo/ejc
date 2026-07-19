"""086 — users.totp_secret VARCHAR(64) → VARCHAR(255) (segredo TOTP cifrado)

Auditoria pré-produção (item 4): o segredo TOTP passa a ser gravado CIFRADO
com Fernet (mesma infra pii_crypto de CPF/CNPJ). O token Fernet de um segredo
base32 de 32 chars tem ~140 caracteres — não cabia no VARCHAR(64) original.

SEM migração de dados: segredos legados em texto claro continuam válidos
(a leitura em routers/auth.py tenta decifrar e cai para o claro), sendo
re-cifrados oportunisticamente no próximo uso autenticado.

ADITIVO/IDEMPOTENTE: alargar VARCHAR nunca perde dado; rodar 2x é inócuo.

Revision ID: 086_totp_secret_cifrado
Revises: 085_nfse
Create Date: 2026-07-12
"""
from alembic import op

revision = "086_totp_secret_cifrado"
down_revision = "085_nfse"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE users ALTER COLUMN totp_secret TYPE VARCHAR(255)")


def downgrade():
    # Encolher só é seguro se nenhum valor cifrado (>64) existir; trunca não —
    # falha alto se houver, o que é o comportamento correto para não corromper.
    op.execute("ALTER TABLE users ALTER COLUMN totp_secret TYPE VARCHAR(64)")
