# ── alembic/env.py ────────────────────────────────────────────────────────────
# Alembic usa driver SYNC (psycopg2) — DATABASE_URL_SYNC do .env.
import os
import sys
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import Base
import app.models  # noqa — registra todos os modelos no metadata

config = context.config

# URL do .env (nunca hardcode)
db_url = os.environ.get(
    "DATABASE_URL_SYNC",
    "postgresql://ejc_user:ejc_pass@db:5432/ejc_db",
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
        context.configure(
            connection=connection, target_metadata=target_metadata,
            include_name=include_name,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
