
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event


def _uid() -> str:
    """Generates a unique event_id for each test run to avoid conflicts."""
    return f"test_{uuid.uuid4().hex[:12]}"


def _event_payload(event_id: str, **overrides) -> dict:
    """Returns a valid event payload with sensible defaults."""
    base = {
        "event_id": event_id,
        "tenant_id": "tenant_api_test",
        "source": "web",
        "event_type": "click",
        "timestamp": "2024-06-01T10:00:00Z",
        "payload": {"user_id": 42},
    }
    base.update(overrides)
    return base



# ─────────────────────────────────────────────
# POST /events — Single Ingestion
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_single_event_returns_202(client: AsyncClient):
    """A valid event should be accepted with HTTP 202."""
    response = await client.post("/events", json=_event_payload(_uid()))
    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}


@pytest.mark.asyncio
async def test_single_event_persisted_in_db(client: AsyncClient, db: AsyncSession):
    """After insertion the event must exist in the DB with correct fields."""
    eid = _uid()
    payload = _event_payload(eid, source="mobile", event_type="view")
    await client.post("/events", json=payload)

    result = await db.execute(select(Event).where(Event.event_id == eid))
    event = result.scalar_one_or_none()

    assert event is not None
    assert event.tenant_id == "tenant_api_test"
    assert event.source == "mobile"
    assert event.event_type == "view"


@pytest.mark.asyncio
async def test_single_event_idempotency(client: AsyncClient, db: AsyncSession):
    """
    Sending the same event_id twice must result in exactly ONE row in the DB.
    HTTP response must be 202 both times (not an error on the duplicate).
    """
    eid = _uid()
    payload = _event_payload(eid)

    r1 = await client.post("/events", json=payload)
    r2 = await client.post("/events", json=payload)

    assert r1.status_code == 202
    assert r2.status_code == 202  # duplicate is silently ignored, not rejected

    count = await db.scalar(select(func.count()).where(Event.event_id == eid))
    assert count == 1


@pytest.mark.asyncio
async def test_single_event_missing_required_field_returns_422(client: AsyncClient):
    """A payload missing 'tenant_id' must be rejected by Pydantic with HTTP 422."""
    payload = {
        "event_id": _uid(),
        # tenant_id intentionally omitted
        "source": "web",
        "event_type": "click",
        "timestamp": "2024-06-01T10:00:00Z",
        "payload": {},
    }
    response = await client.post("/events", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_single_event_invalid_timestamp_returns_422(client: AsyncClient):
    """A payload with a malformed timestamp must fail validation."""
    payload = _event_payload(_uid(), timestamp="not-a-date")
    response = await client.post("/events", json=payload)
    assert response.status_code == 422


# ─────────────────────────────────────────────
# POST /events/bulk — Batch Ingestion
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bulk_insert_returns_202_with_count(client: AsyncClient):
    """Bulk insert should return 202 and echo back how many events were received."""
    events = [_event_payload(_uid()) for _ in range(5)]
    response = await client.post("/events/bulk", json=events)
    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
    assert response.json()["received"] == 5


@pytest.mark.asyncio
async def test_bulk_insert_all_events_persisted(client: AsyncClient, db: AsyncSession):
    """All unique events in a bulk payload must be written to the DB."""
    ids = [_uid() for _ in range(4)]
    events = [_event_payload(eid) for eid in ids]

    await client.post("/events/bulk", json=events)

    for eid in ids:
        count = await db.scalar(select(func.count()).where(Event.event_id == eid))
        assert count == 1, f"Expected event {eid} to exist in DB"


@pytest.mark.asyncio
async def test_bulk_insert_deduplicates_within_batch(client: AsyncClient, db: AsyncSession):
    """
    A batch containing duplicate event_ids must only persist ONE row per unique id.
    The endpoint must still return 202 — duplicates are silently ignored.
    """
    eid = _uid()
    events = [
        _event_payload(eid, event_type="click"),   # first occurrence
        _event_payload(_uid()),                     # unique
        _event_payload(eid, event_type="view"),    # duplicate — should be ignored
    ]
    response = await client.post("/events/bulk", json=events)
    assert response.status_code == 202
    assert response.json()["received"] == 3  # API received 3

    count = await db.scalar(select(func.count()).where(Event.event_id == eid))
    assert count == 1  # but only 1 stored


@pytest.mark.asyncio
async def test_bulk_insert_cross_batch_idempotency(client: AsyncClient, db: AsyncSession):
    """
    An event_id already in the DB from a previous request must not be duplicated
    by a later bulk insert containing the same event_id.
    """
    eid = _uid()
    # First: single insert
    await client.post("/events", json=_event_payload(eid))

    # Second: bulk insert containing the same event_id
    await client.post("/events/bulk", json=[_event_payload(eid), _event_payload(_uid())])

    count = await db.scalar(select(func.count()).where(Event.event_id == eid))
    assert count == 1


@pytest.mark.asyncio
async def test_bulk_insert_empty_list_returns_202(client: AsyncClient):
    """An empty bulk payload should be handled gracefully."""
    response = await client.post("/events/bulk", json=[])
    assert response.status_code == 202
    assert response.json()["received"] == 0


@pytest.mark.asyncio
async def test_bulk_insert_invalid_event_in_batch_returns_422(client: AsyncClient):
    """If any event in the batch fails Pydantic validation, the whole request is rejected."""
    events = [
        _event_payload(_uid()),
        {"event_id": _uid(), "source": "web"},  # missing required fields
    ]
    response = await client.post("/events/bulk", json=events)
    assert response.status_code == 422
