"""058_users_email_unique — BUG-09: UNIQUE(email) em users

Garante unicidade de e-mail no nível do banco (o model já declara unique=True,
mas produção pode não ter a constraint). Previne recriação de usuários
duplicados após o merge/dedup.

⚠️ ORDEM: aplicar SOMENTE APÓS o merge de usuários duplicados
(scripts/merge_usuarios_duplicados.sql). Se houver e-mails repetidos, a criação
do índice único FALHA. Em produção os e-mails já são distintos (auditoria).

Idempotente: CREATE UNIQUE INDEX IF NOT EXISTS.

Revision ID: 058_users_email_unique
Revises: 057_deadline_datajud
"""
from alembic import op

revision = "058_users_email_unique"
down_revision = "057_deadline_datajud"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Índice único (equivalente a UNIQUE(email)); nome distinto do índice comum
    # ix_users_email que já existe (index=True no model). Idempotente.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email "
        "ON users(email)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_users_email")
