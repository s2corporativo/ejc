"""Alembic ``alembic_version.version_num`` padronizada em ``varchar(128)``.

A revision 143 possui identificador com mais de 32 caracteres. Para bancos
limpos, ``alembic/env.py`` garante preventivamente que a tabela interna de
versão já tenha capacidade suficiente antes de qualquer migration ser gravada.
Esta revision permanece como declaração canônica e expand-only do schema de
metadados para ambientes legados que ainda cheguem à cadeia com varchar(32).

O ``upgrade()`` é widening estática 32→128 e não altera dados de negócio.
O ``downgrade()`` não reduz a coluna: o alvo imediato é a própria revision 143,
cujo identificador não cabe em varchar(32). Encolher aqui faria o Alembic falhar
quando tentasse registrar a revisão de destino. Manter varchar(128) no rollback
é compatível, não destrutivo e preserva a capacidade de continuar a navegação
da cadeia para trás.
"""

from alembic import op
import sqlalchemy as sa

revision = "144_alembic_version_varchar128"
down_revision = "143_signature_documento_visualizado"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Widening estrita e estática: varchar(32) -> varchar(128). O bootstrap do
    # env.py pode já ter ampliado fisicamente a coluna; repetir o TYPE 128 no
    # PostgreSQL é seguro e mantém esta migration compatível com o gate de deploy.
    op.alter_column(
        "alembic_version",
        "version_num",
        type_=sa.String(128),
        existing_type=sa.String(32),
    )


def downgrade() -> None:
    # Intencionalmente não encolhe para varchar(32): ao concluir o downgrade
    # desta revision, o Alembic precisa gravar ``143_signature_documento_visualizado``
    # (35 caracteres). Reduzir antes dessa gravação quebraria o próprio rollback.
    pass
