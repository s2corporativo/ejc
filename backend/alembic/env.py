# ── alembic/env.py ────────────────────────────────────────────────────────────
# Alembic usa driver SYNC (psycopg2). Em produção, prefira a credencial
# exclusiva de migração via MIGRATION_DATABASE_URL; DATABASE_URL_SYNC permanece
# como fallback temporário/compatibilidade para desenvolvimento e rollout.
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Column, MetaData, String, Table, engine_from_config, inspect, pool, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import Base
import app.models  # noqa — registra todos os modelos no metadata

config = context.config

# URL do .env (nunca hardcode)
db_url = (
    (os.environ.get("MIGRATION_DATABASE_URL") or "").strip()
    or (os.environ.get("DATABASE_URL_SYNC") or "").strip()
    or "postgresql://ejc_user:ejc_pass@db:5432/ejc_db"
)
config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# ── Colunas VIVAS no banco mas SEM atributo no ORM ────────────────────────────
# ~13 colunas REAIS acessadas por SQL cru (não mapeadas em app/models/), cujas
# TABELAS têm model — então o autogenerate compara as colunas e, cego, proporia
# op.drop_column() para cada uma: foot-gun destrutivo (perda de dados) se a
# revisão fosse aplicada. Esta allowlist faz a guarda IGNORÁ-LAS por (tabela,
# coluna). BANCO É FONTE DA VERDADE — mantenha sincronizada quando uma coluna
# raw-SQL for adicionada/removida. NÃO altera migrations existentes nem o schema;
# só filtra a GERAÇÃO de novas revisões. (Tabelas SEM model são tratadas pela
# guarda de tabela em include_name; aqui cuidamos das colunas em tabelas COM
# model.)
_COLUNAS_VIVAS_FORA_DO_ORM: set[tuple[str, str]] = {
    ("documents", "download_count"),
    ("documents", "sensitivity_level"),
    ("documents", "watermark"),
    ("documents", "access_users"),
    ("documents", "last_accessed_at"),
    ("cases", "indice_risco"),
    ("cases", "risco_nivel"),
    ("cases", "risco_fatores"),
    ("cases", "risco_atualizado_em"),
    ("teses", "area_direito"),
    ("knowledge_chunks", "categoria"),
    ("checklist_templates", "tipo_demanda"),
}

# Alembic cria a tabela interna ``alembic_version`` com VARCHAR(32) por padrão.
# A revision 143 possui identificador maior que 32 caracteres; em banco limpo,
# esperar a migration 144 para ampliar a coluna é tarde demais, pois o Alembic
# precisa gravar a própria 143 antes de chegar à 144. O bootstrap abaixo atua
# SOMENTE na tabela de metadados do Alembic, antes da cadeia de migrations:
# cria-a já com margem suficiente ou amplia de forma idempotente instalações
# antigas. Não toca tabelas/dados jurídicos e não altera a numeração da cadeia.
_ALEMBIC_VERSION_LENGTH = 128


def _ensure_alembic_version_capacity(connection) -> None:
    """Garante capacidade para revision IDs longas antes de ``run_migrations``.

    A correção é deliberadamente restrita ao PostgreSQL, banco suportado pelo
    EJC em produção/CI. Widening de VARCHAR é não destrutivo. Em ambientes já
    adequados, a função não emite ALTER.
    """
    if connection.dialect.name != "postgresql":
        return

    inspector = inspect(connection)
    if not inspector.has_table("alembic_version"):
        metadata = MetaData()
        version_table = Table(
            "alembic_version",
            metadata,
            Column(
                "version_num",
                String(_ALEMBIC_VERSION_LENGTH),
                nullable=False,
                primary_key=True,
            ),
        )
        version_table.create(connection, checkfirst=True)
        return

    columns = {
        column["name"]: column
        for column in inspector.get_columns("alembic_version")
    }
    version_column = columns.get("version_num")
    if version_column is None:
        raise RuntimeError(
            "alembic_version existe sem a coluna version_num; "
            "estado de metadados inválido — intervenção manual necessária"
        )

    current_length = getattr(version_column["type"], "length", None)
    if current_length is not None and current_length < _ALEMBIC_VERSION_LENGTH:
        connection.execute(
            text(
                "ALTER TABLE alembic_version "
                "ALTER COLUMN version_num TYPE VARCHAR(128)"
            )
        )


def include_name(name, type_, parent_names):
    """Guarda de segurança do autogenerate (Etapa 6).

    O EJC tem ~30 tabelas de acesso 100% SQL cru (agenda_eventos, jur_*,
    kanban_columns, office_*, portal_mensagens, etc.) que existem no banco mas
    NÃO têm model ORM — logo não estão em Base.metadata. Sem esta guarda, um
    `alembic revision --autogenerate` geraria `op.drop_table(...)` para todas
    elas: foot-gun destrutivo (perda de dados) se a migração fosse aplicada.

    Restringir o autogenerate às tabelas presentes no metadata impede esses
    drops espúrios. NÃO afeta upgrade/downgrade das migrations já existentes —
    só a GERAÇÃO de novas revisões. Índices/constraints (type_ != "table")
    seguem o padrão normal.

    Camada de COLUNA (filtro por nome): colunas vivas fora do ORM
    (_COLUNAS_VIVAS_FORA_DO_ORM) são ignoradas para o autogenerate não propor
    op.drop_column() — complementada por include_object (filtro por objeto).
    """
    if type_ == "table":
        return name in target_metadata.tables
    if type_ == "column":
        tabela = (parent_names or {}).get("table_name")
        if (tabela, name) in _COLUNAS_VIVAS_FORA_DO_ORM:
            return False
    return True


def include_object(object_, name, type_, reflected, compare_to):
    """Complementa include_name no nível de OBJETO: barra o DROP das colunas
    vivas fora do ORM. Uma coluna presente SÓ no banco (reflected=True) e SEM
    contraparte no metadata (compare_to is None) é exatamente o caso de "remover
    coluna" que o autogenerate proporia — devolvê-la como excluída (False)
    impede o op.drop_column(). O guard `reflected and compare_to is None` garante
    que colunas LOCAIS do model (as que devem existir) nunca são afetadas.
    """
    if type_ == "column" and reflected and compare_to is None:
        tabela = getattr(getattr(object_, "table", None), "name", None)
        if (tabela, name) in _COLUNAS_VIVAS_FORA_DO_ORM:
            return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_name=include_name,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # Executa e confirma o bootstrap isoladamente antes de o Alembic iniciar
        # a própria transação de migrations. Assim uma instalação limpa já nasce
        # apta a registrar a revision 143, e ambientes existentes só sofrem
        # widening quando realmente necessário.
        with connection.begin():
            _ensure_alembic_version_capacity(connection)

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_name=include_name,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
