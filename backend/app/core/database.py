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
    """Verifica conectividade com o banco (usado no /health/ready).

    Resiliente ao cross-loop dos testes: o pool do engine pode reter conexões
    asyncpg presas a um event loop já fechado (pytest-asyncio/TestClient criam
    um loop por chamada). A 1ª tentativa então falha com RuntimeError ("got
    Future attached to a different loop" / "Event loop is closed") — que NÃO é o
    banco fora do ar. Nesse caso descartamos o pool poluído (dispose(close=False)
    abandona as conexões do loop morto sem aguardar close nelas) e refazemos numa
    conexão nova. Em produção (loop único do uvicorn) a 1ª tentativa já passa e o
    dispose nunca roda. DB realmente fora → ambas as tentativas falham → False.
    """
    async def _probe() -> None:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.execute(text("SELECT 1 FROM pg_extension WHERE extname='vector'"))

    try:
        await _probe()
        return True
    except Exception as e:
        if "loop" in str(e).lower():
            # Artefato de cross-loop do pool sob teste — reseta e reconsulta.
            try:
                await engine.dispose(close=False)
                await _probe()
                return True
            except Exception as e2:
                logger.error(f"Database check failed after pool reset: {e2}")
                return False
        logger.error(f"Database check failed: {e}")
        return False
