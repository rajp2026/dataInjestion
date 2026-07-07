import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import engine, Base

# DB clearing removed to avoid asyncpg concurrent connection issues
# Tests will use unique event IDs to avoid conflicts.

@pytest_asyncio.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
