# ── alembic/env.py — variante ASSÍNCRONA (asyncpg) ────────────────────────────
# O projeto usa asyncpg (não há driver sync instalado). Este env.py roda as
# migrations sobre o engine assíncrono, evitando depender de psycopg2.
#
# Importa TODOS os submódulos de app.models para que Base.metadata fique
# COMPLETO (o app/models/__init__.py importa só parte dos modelos).
# ──────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import asyncio
import importlib
import pkgutil
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config, AsyncEngine
from alembic import context

from app.core.config import get_settings
from app.core.database import Base
import app.models as _models_pkg


def _import_all_models() -> None:
    """Importa todos os módulos sob app.models para popular Base.metadata."""
    for _, name, _is_pkg in pkgutil.iter_modules(_models_pkg.__path__):
        importlib.import_module(f"app.models.{name}")


_import_all_models()

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
# URL injetada a partir das settings (asyncpg) — nunca hardcodada no .ini.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable: AsyncEngine = async_engine_from_config(
        {"sqlalchemy.url": settings.DATABASE_URL},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
