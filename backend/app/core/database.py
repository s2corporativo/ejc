# ── app/core/database.py ─────────────────────────────────────────────────────
# Engine async (asyncpg), session factory e Base declarativa.
# Todos os modelos SQLAlchemy importam Base daqui para o Alembic detectar.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from app.core.config import get_settings
import logging

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Engine principal ──────────────────────────────────────────────────────────
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,   # testa conexão antes de usar (evita erros de timeout)
    pool_size=10,
    max_overflow=20,
    echo=settings.DEBUG,
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


# ── Dependency injection para FastAPI ─────────────────────────────────────────
async def get_db() -> AsyncSession:
    """
    Injeta AsyncSession em cada request via FastAPI Depends().
    Garante rollback e fechamento mesmo em caso de erro.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def check_db() -> bool:
    """Verifica conectividade com o banco (usado no /health)."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.execute(text("SELECT 1 FROM pg_extension WHERE extname='vector'"))
        return True
    except Exception as e:
        logger.error(f"Database check failed: {e}")
        return False
