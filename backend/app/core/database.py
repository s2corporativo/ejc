# ── app/core/database.py ─────────────────────────────────────────────────────
# Engine async (asyncpg), session factory e Base declarativa.
# Todos os modelos SQLAlchemy importam Base daqui para o Alembic detectar.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

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


# ── Dependency injection para FastAPI ────────────────────────────────────────
async def get_db() -> AsyncSession:
    """Injeta uma sessão e garante rollback/fechamento em caso de erro."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def check_db() -> bool:
    """Verifica conectividade e a extensão pgvector.

    O fallback de descarte do pool cobre processos de desenvolvimento que
    executem verificações em loops diferentes. Em CI com NullPool, a primeira
    tentativa já usa uma conexão nova.
    """

    async def _probe() -> None:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.execute(
                text("SELECT 1 FROM pg_extension WHERE extname='vector'")
            )

    try:
        await _probe()
        return True
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
