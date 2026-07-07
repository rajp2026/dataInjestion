import pytest
from httpx import AsyncClient
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.event import Event

@pytest.mark.asyncio
async def test_create_event_success(client: AsyncClient):
    payload = {
        "event_id": "test_event_1",
        "tenant_id": "tenant_1",
        "source": "web",
        "event_type": "click",
        "timestamp": "2023-01-01T12:00:00Z",
        "payload": {"user_id": 123}
    }
    response = await client.post("/events", json=payload)
    assert response.status_code == 202
    
    # Verify the event was actually written to the DB
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Event).where(Event.event_id == "test_event_1"))
        event = result.scalar_one_or_none()
        assert event is not None
        assert event.tenant_id == "tenant_1"

@pytest.mark.asyncio
async def test_create_event_idempotency(client: AsyncClient):
    payload = {
        "event_id": "test_event_2",
        "tenant_id": "tenant_1",
        "source": "web",
        "event_type": "click",
        "timestamp": "2023-01-01T12:00:00Z",
        "payload": {"user_id": 123}
    }
    
    # Send the first request
    response1 = await client.post("/events", json=payload)
    assert response1.status_code == 202
    
    # Send the exact same request again (same event_id)
    response2 = await client.post("/events", json=payload)
    assert response2.status_code == 202 
    
    # Verify ONLY ONE event exists in the database
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Event).where(Event.event_id == "test_event_2"))
        events = result.scalars().all()
        assert len(events) == 1

@pytest.mark.asyncio
async def test_create_event_validation_error(client: AsyncClient):
    payload = {
        "event_id": "test_event_3",
        # Missing tenant_id, should trigger Pydantic validation error
        "source": "web",
        "event_type": "click",
        "timestamp": "2023-01-01T12:00:00Z",
        "payload": {}
    }
    response = await client.post("/events", json=payload)
    assert response.status_code == 422 
