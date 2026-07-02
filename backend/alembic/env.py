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
    """
    if type_ == "table":
        return name in target_metadata.tables
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_name=include_name,
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
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
