# ── app/core/database.py ─────────────────────────────────────────────────────
# Engine async (asyncpg), session factory e Base declarativa.
# Todos os modelos SQLAlchemy importam Base daqui para o Alembic detectar.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Em CI, pytest-asyncio pode criar mais de um event loop ao longo da suíte. Um
# pool asyncpg persistente não pode reutilizar conexões ligadas a um loop já
# encerrado. NullPool abre/fecha uma conexão por sessão apenas quando
# RUN_DB_TESTS=1; produção mantém o pool dimensionado abaixo.
_engine_kwargs: dict[str, Any] = {
    "pool_pre_ping": True,
    "echo": settings.DEBUG,
}
if os.getenv("RUN_DB_TESTS"):
    _engine_kwargs["poolclass"] = NullPool
else:
    _engine_kwargs.update(pool_size=10, max_overflow=20)

# ── Engine principal ─────────────────────────────────────────────────────────
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    **_engine_kwargs,
)

# ── Session factory ───────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


# ── Base declarativa ─────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


def runtime_ddl_permitido(db: object) -> bool:
    """Permite DDL de conveniência somente em SQLite de testes.

    PostgreSQL é schema-managed por Alembic. Fakes sem get_bind também
    retornam False, evitando que testes unitários dependam de CREATE TABLE.
    """
    get_bind = getattr(db, "get_bind", None)
    if not callable(get_bind):
        return False
    try:
        bind = get_bind()
    except Exception:
        return False
    return getattr(getattr(bind, "dialect", None), "name", None) == "sqlite"


# ── Dependency injection para FastAPI ────────────────────────────────────────
async def get_db() -> AsyncSession:
    """Injeta uma sessão e garante rollback/fechamento em caso de erro."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def check_db(timeout: float | None = None) -> bool:
    """Verifica conectividade e a extensão pgvector.

    O fallback de descarte do pool cobre processos de desenvolvimento que
    executem verificações em loops diferentes. Em CI com NullPool, a primeira
    tentativa já usa uma conexão nova.

    TIMEOUT OBRIGATÓRIO (incidente de 04/09/2026): esta função é a PRIMEIRA
    coisa que o `lifespan` do FastAPI executa. Sem teto de tempo, um Postgres
    alcançável mas travado (lock, disco cheio, saturação da VPS compartilhada)
    prende o startup para sempre — o uvicorn já fez o bind do socket, então o
    kernel ACEITA a conexão TCP e nunca a serve. Sintoma medido em produção:
    nginx devolvendo 504 após os 120 s de `proxy_read_timeout` até para rota
    inexistente, enquanto o SPA estático respondia em 0,5 s. O `except Exception`
    abaixo NÃO cobria isso: travamento não levanta exceção.
    """
    limite = settings.STARTUP_STEP_TIMEOUT_SECONDS if timeout is None else timeout

    async def _probe() -> None:
        # limite <= 0 desativa o teto (asyncio.timeout(None) = sem prazo).
        async with asyncio.timeout(limite if limite and limite > 0 else None):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                await conn.execute(
                    text("SELECT 1 FROM pg_extension WHERE extname='vector'")
                )

    try:
        await _probe()
        return True
    except TimeoutError:
        logger.error(
            "Database check ESGOTOU O TEMPO (%.1fs) — banco alcançável porém "
            "sem resposta. O boot segue em modo degradado para a API responder; "
            "investigue o Postgres (locks, disco, carga).", limite,
        )
        return False
    except Exception as exc:
        if "loop" in str(exc).lower():
            try:
                await engine.dispose(close=False)
                await _probe()
                return True
            except Exception as retry_exc:
                logger.error(
                    "Database check failed after pool reset: %s", retry_exc
                )
                return False
        logger.error("Database check failed: %s", exc)
        return False
