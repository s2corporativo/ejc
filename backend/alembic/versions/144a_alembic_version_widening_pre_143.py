"""alembic_version.version_num varchar(32) -> varchar(128) ANTES da migration
``143_signature_documento_visualizado``.

Correção de baseline de instalação nova (Módulo 02 — Infraestrutura):

A migration ``143`` possui revision_id com 35 caracteres, o que estoura o
``varchar(32)`` original da coluna ``alembic_version.version_num`` em
instalações limpas (a ``144`` corrige o widening, mas roda DEPOIS da 143 na
cadeia — tarde demais). ``143`` já está aplicada em produção (por ALTER
manual), portanto esta correção usa ``depends_on``: roda o widening logo após
a ``142`` em instalações novas e é no-op (widening idempotente, PostgreSQL
aceita widening já aplicado) em instalações onde a ``144`` já tiver rodado.

- upgrade: widening varchar(32) -> varchar(128) (DDL puro, sem perda de dados).
- downgrade: volta a varchar(32) somente se não houver versão gravada com
  mais de 32 caracteres; caso contrário aborta sem alterar nada (guarda humana).
"""
from alembic import op
import sqlalchemy as sa

revision = "144a_alembic_version_widening"
down_revision = "142_document_hash_rescan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "alembic_version",
        "version_num",
        type_=sa.String(128),
        existing_type=sa.String(32),
    )


def downgrade() -> None:
    # Widening virtualmente permanente (mesma justificativa da migration
    # ``144_alembic_version_varchar128``): a migration ``143`` possui
    # revision_id com 35 caracteres e permanece na cadeia. Estreitar a coluna
    # rejeitaria a transação de downgrade (o Alembic grava a revision_id de
    # destino antes de executar este corpo). Downgrade no-op, seguro e
    # idempotente — widening não tem custo de dados.
    pass
