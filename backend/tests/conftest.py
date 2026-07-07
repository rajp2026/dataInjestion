import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.database import SQLALCHEMY_DATABASE_URL, get_db

# Separate NullPool engine for testing
# NullPool: no connection reuse — each await gets a fresh DB connection
_test_engine = create_async_engine(SQLALCHEMY_DATABASE_URL, poolclass=NullPool)
_TestSessionLocal = async_sessionmaker(
    _test_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


async def _override_get_db():
    """Replaces the real get_db with a NullPool-backed session during tests."""
    async with _TestSessionLocal() as session:
        yield session


# Override FastAPI's DB dependency globally for all tests
app.dependency_overrides[get_db] = _override_get_db


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    """Function-scoped NullPool DB session — fresh connection per test, no sharing."""
    async with _TestSessionLocal() as session:
        yield session
