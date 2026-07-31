import uuid
"""
Fixtures compartilhadas — usa banco PostgreSQL ejc_test (isolado de produção).
Roda create_all / drop_all por função para garantir isolamento entre testes.
"""
import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.main import app
from app.core.database import get_db, Base
from app.core.security import get_password_hash, create_access_token
from app.models.user import User, UserRole

_DB_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL_TEST")


@pytest_asyncio.fixture(scope="function")
async def db_session():
    if not _DB_URL or not _DB_URL.startswith("postgresql"):
        pytest.skip("Defina TEST_DATABASE_URL com PostgreSQL/pgvector para testes de banco.")
    if "ejc_db" in _DB_URL and "test" not in _DB_URL.lower():
        pytest.skip("TEST_DATABASE_URL parece apontar para banco nao isolado; pulando por seguranca.")
    engine = create_async_engine(_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession):
    async def _override_db():
        yield db_session
    app.dependency_overrides[get_db] = _override_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession):
    user = User(
        id=str(uuid.uuid4()),
        full_name="Admin Teste",
        email="admin@ejctest.com",
        hashed_password=get_password_hash("Senha@123"),
        role=UserRole.admin,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_token(admin_user: User):
    return create_access_token(str(admin_user.id), admin_user.role.value)


@pytest_asyncio.fixture
async def auth_headers(admin_token: str):
    return {"Authorization": f"Bearer {admin_token}"}
