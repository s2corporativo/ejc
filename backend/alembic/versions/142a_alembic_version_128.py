"""Expande ``alembic_version.version_num`` antes da revision longa 143.

Compatibilidade para instalações limpas: o Alembic cria ``version_num`` como
``varchar(32)`` por padrão, enquanto a revision seguinte
``143_signature_documento_visualizado`` possui 35 caracteres. Sem esta ponte,
o DDL da 143 executa, mas a gravação do identificador da própria migration
falha por truncamento.

A migration é expand-only: apenas amplia varchar(32) para varchar(128), sem
alterar dados de negócio. Produções que já avançaram além da 143 não voltam a
executá-la, pois ela passa a ser ancestral da head existente.
"""

from alembic import op
import sqlalchemy as sa

revision = "142a_alembic_version_128"
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
    # Neste ponto a versão corrente é esta própria revision (<= 32 chars),
    # portanto a redução é segura desde que nenhuma linha anômala exceda 32.
    conn = op.get_bind()
    (excede,) = conn.execute(
        sa.text(
            "SELECT COALESCE(bool_or(char_length(version_num) > 32), false) "
            "FROM alembic_version"
        )
    ).one()
    if excede:
        raise RuntimeError(
            "downgrade 142a: existe version_num com mais de 32 caracteres; "
            "redução abortada para impedir truncamento"
        )
    op.alter_column(
        "alembic_version",
        "version_num",
        type_=sa.String(32),
        existing_type=sa.String(128),
    )
