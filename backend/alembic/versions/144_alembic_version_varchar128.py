"""Alembic ``alembic_version.version_num`` padronizada em ``varchar(128)``.

Correção do deploy de 15/08/2026: o ``alembic upgrade`` da migration
``143_signature_documento_visualizado`` (revision_id com 35 caracteres)
estourava o ``varchar(32)`` original da coluna, rejeitando a transação em
ambientes novos ou reinstalações limpas — o banco do deploy em produção só
prosseguia após o ALTER manual.

Aumentar a margem em vez de abreviar as revision_ids: mantém os nomes
descritivos existentes (141/142/143) e folga confortável para o crescimento
da cadeia sem nova emergência. Operação segura: ``ALTER COLUMN ... TYPE``
em ``varchar`` mais largo nunca perde dados; idempotente por consulta ao
``information_schema`` antes do ALTER (protege re-execução em qualquer
estágio, inclusive nos ambientes que já receberam o ajuste manual).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "144_alembic_version_varchar128"
down_revision = "143_signature_documento_visualizado"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    (data_type, length) = conn.execute(
        text(
            "SELECT data_type, character_maximum_length "
            "FROM information_schema.columns "
            "WHERE table_name = 'alembic_version' "
            "AND column_name = 'version_num'"
        )
    ).one()
    # Já padronizada: produção (ajuste manual de 15/08) e instalações novas
    # que passem por esta migration sem precisar do ALTER.
    if data_type == "character varying" and length is not None and int(length) >= 128:
        return
    op.alter_column(
        "alembic_version", "version_num",
        type_=sa.VARCHAR(128),
        existing_type=sa.VARCHAR(32),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Rollback para o padrão original (varchar(32)), que comporta todas as
    # revision_ids da cadeia até a 142 (24 chars). Falha explicitamente se
    # houver qualquer versão gravada com mais de 32 caracteres — proteção
    # contra truncamento silencioso: aborta sem alterar nada.
    conn = op.get_bind()
    (excede,) = conn.execute(
        text(
            "SELECT COALESCE(bool_or(char_length(version_num) > 32), false) "
            "FROM alembic_version"
        )
    ).one()
    if excede:
        raise RuntimeError(
            "downgrade 144: existe versão gravada com mais de 32 caracteres; "
            "restringir a coluna trunca a linha atual — abortando sem alterar nada"
        )
    op.alter_column(
        "alembic_version", "version_num",
        type_=sa.VARCHAR(32),
        existing_type=sa.VARCHAR(128),
        existing_nullable=False,
    )
