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

**Homologação M02/M11 (16/08/2026):** o widening foi consolidado no upgrade
da ``143`` (onde precisa rodar, antes da gravação do ``revision_id`` de 35
caracteres). Esta migration executa o widening novamente como operação
idempotente — PostgreSQL aceita widening já aplicado sem alterar nada — e
preserva o ``downgrade()`` no-op seguro: estreitar aqui rejeitaria a
própria transação de downgrade, pois o Alembic grava a ``revision_id`` de
destino antes de executar o corpo.
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
    # Widening virtualmente permanente: a migration ``143`` (revision_id com
    # 35 caracteres) segue esta na cadeia de downgrade. O Alembic grava a
    # revision_id de DESTINO (143) antes de executar este corpo — estreitar
    # aqui rejeitaria a transação mesmo com o banco "limpo" (bug reproduzido
    # no Módulo 02, 15/08/2026). Como widening não tem custo de dados e
    # varchar(128) cabe confortavelmente o histórico, o estreitamento é
    # desabilitado: downgrade é no-op seguro e idempotente.
    pass
