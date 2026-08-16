"""Mantém ``alembic_version.version_num`` padronizada em ``varchar(128)``.

A ponte ``142a_alembic_version_128`` agora realiza o widening antes da revision
143, resolvendo instalações limpas. Esta revision 144 permanece na cadeia por
compatibilidade com ambientes que já a registraram e reafirma o tipo esperado.

O downgrade é deliberadamente não destrutivo: o alvo imediato é
``143_signature_documento_visualizado``, cujo identificador possui 35 caracteres.
Reduzir a coluna para varchar(32) antes de o Alembic gravar esse alvo tornaria o
próprio rollback impossível. A redução segura para varchar(32) ocorre somente no
downgrade da ponte 142a, depois que a cadeia já voltou a uma revision curta.
"""

from alembic import op
import sqlalchemy as sa

revision = "144_alembic_version_varchar128"
down_revision = "143_signature_documento_visualizado"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotente quanto ao tipo efetivo: reafirma varchar(128), necessário
    # também para instalações que chegaram à 143 por correção operacional antiga.
    op.alter_column(
        "alembic_version",
        "version_num",
        type_=sa.String(128),
        existing_type=sa.String(128),
    )


def downgrade() -> None:
    # Não reduzir aqui: após este método o Alembic precisa gravar a revision 143
    # (35 caracteres). A ponte 142a executa a redução quando for seguro.
    pass
