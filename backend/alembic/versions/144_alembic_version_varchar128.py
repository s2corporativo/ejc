"""Alembic ``alembic_version.version_num`` padronizada em ``varchar(128)``.

Correção do deploy de 15/08/2026: o ``alembic upgrade`` da migration
``143_signature_documento_visualizado`` (revision_id com 35 caracteres)
estourava o ``varchar(32)`` original da coluna, rejeitando a transação em
ambientes novos ou reinstalações limpas — o banco do deploy em produção só
prosseguia após o ALTER manual.

Aumentar a margem em vez de abreviar as revision_ids: mantém os nomes
descritivos existentes (141/142/143) e folga confortável para o crescimento
da cadeia sem nova emergência. ``upgrade()`` é DDL puro e estático
(widening de ``varchar(32)`` para ``varchar(128)``): PostgreSQL nunca
recusa dados existentes em widening, e instalações novas seguem o caminho
padrão sem condicionais — o gate de compatibilidade de deploy aprova.

O ``downgrade()`` reverte para ``varchar(32)`` com guarda humana:
aborta sem alterar nada se houver versão gravada com mais de 32
caracteres (nenhuma existe na cadeia até a 144, pois 142 tem 24 chars).
"""
from alembic import op
import sqlalchemy as sa

revision = "144_alembic_version_varchar128"
down_revision = "143_signature_documento_visualizado"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Widening estrita e estática: varchar(32) -> varchar(128). DDL puro,
    # expand-only — nenhuma linha é alterada ou perdida.
    op.alter_column(
        "alembic_version",
        "version_num",
        type_=sa.String(128),
        existing_type=sa.String(32),
    )


def downgrade() -> None:
    # Reverte para varchar(32). Aborta sem alterar nada se alguma
    # version_num gravada exceder 32 caracteres — proteção contra
    # truncamento silencioso de linhas já registradas.
    conn = op.get_bind()
    (excede,) = conn.execute(
        sa.text(
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
        "alembic_version",
        "version_num",
        type_=sa.String(32),
        existing_type=sa.String(128),
    )
