import pytest
from httpx import AsyncClient
from unittest.mock import patch

@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """
    GET /health should return 200 OK and {"status": "ok"}
    """
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

@pytest.mark.asyncio
async def test_readiness_check_success(client: AsyncClient):
    """
    GET /ready should return 200 OK and {"status": "ready"} when DB is accessible.
    """
    response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}

@pytest.mark.asyncio
async def test_readiness_check_failure(client: AsyncClient):
    """
    GET /ready should return 503 if DB connection fails.
    We mock the DB session's execute method to simulate a failure.
    """
    # Create a mock for the db session execute that raises an Exception
    with patch("sqlalchemy.ext.asyncio.AsyncSession.execute", side_effect=Exception("DB Down")):
        response = await client.get("/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "unhealthy", "details": "Database connection failed"}
