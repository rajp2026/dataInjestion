"""
Tests for GET /events and GET /metrics retrieval endpoints.

Strategy:
- GET /events: insert raw events via POST /events, then query and verify filtering/pagination.
- GET /metrics: insert pre-computed aggregate rows directly via DB fixture,
  then verify all filter combinations, bucket sizes, and time ranges.
  (Avoids running the full worker cycle in tests — keeps tests fast and focused.)
"""
import uuid
from datetime import datetime, timezone, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.aggregate import Aggregate


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _tid() -> str:
    """Unique tenant_id per test — avoids cross-test data contamination."""
    return f"tenant_{uuid.uuid4().hex[:8]}"


def _uid() -> str:
    return f"evt_{uuid.uuid4().hex[:10]}"


def _event(event_id: str, tenant_id: str, source: str = "web",
           event_type: str = "click", ts: str = "2024-03-01T10:00:00Z") -> dict:
    return {
        "event_id": event_id,
        "tenant_id": tenant_id,
        "source": source,
        "event_type": event_type,
        "timestamp": ts,
        "payload": {"x": 1},
    }


async def _insert_aggregate_row(
    db: AsyncSession,
    tenant_id: str,
    bucket_start: datetime,
    bucket_size: str,
    source: str = "",
    event_type: str = "",
    count: int = 1,
) -> None:
    """
    Directly inserts a pre-computed aggregate row into the DB.
    Uses ON CONFLICT DO NOTHING so tests can call it freely.
    """
    stmt = pg_insert(Aggregate).values(
        tenant_id=tenant_id,
        bucket_start=bucket_start,
        bucket_size=bucket_size,
        source=source,
        event_type=event_type,
        count=count,
        first_seen=bucket_start,
        last_seen=bucket_start,
    ).on_conflict_do_nothing()
    await db.execute(stmt)
    await db.commit()


# ─────────────────────────────────────────────
# GET /events
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_events_requires_tenant_id(client: AsyncClient):
    """tenant_id is a required query param — omitting it must return 422."""
    r = await client.get("/events")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_list_events_empty_for_unknown_tenant(client: AsyncClient):
    """A tenant with no events must return total=0 and empty data array."""
    r = await client.get("/events", params={"tenant_id": "no_such_tenant"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["data"] == []


@pytest.mark.asyncio
async def test_list_events_returns_inserted_events(client: AsyncClient):
    """Events inserted via POST /events must be queryable via GET /events."""
    tid = _tid()
    ids = [_uid() for _ in range(3)]

    for eid in ids:
        await client.post("/events", json=_event(eid, tid))

    r = await client.get("/events", params={"tenant_id": tid})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert len(body["data"]) == 3


@pytest.mark.asyncio
async def test_list_events_filter_by_source(client: AsyncClient):
    """source filter must return only events matching that source."""
    tid = _tid()
    await client.post("/events", json=_event(_uid(), tid, source="web"))
    await client.post("/events", json=_event(_uid(), tid, source="web"))
    await client.post("/events", json=_event(_uid(), tid, source="mobile"))

    r = await client.get("/events", params={"tenant_id": tid, "source": "web"})
    body = r.json()
    assert body["total"] == 2
    assert all(e["source"] == "web" for e in body["data"])


@pytest.mark.asyncio
async def test_list_events_filter_by_event_type(client: AsyncClient):
    """event_type filter must return only events of that type."""
    tid = _tid()
    await client.post("/events", json=_event(_uid(), tid, event_type="click"))
    await client.post("/events", json=_event(_uid(), tid, event_type="view"))
    await client.post("/events", json=_event(_uid(), tid, event_type="view"))

    r = await client.get("/events", params={"tenant_id": tid, "event_type": "view"})
    body = r.json()
    assert body["total"] == 2
    assert all(e["event_type"] == "view" for e in body["data"])


@pytest.mark.asyncio
async def test_list_events_filter_by_source_and_event_type(client: AsyncClient):
    """Combined source + event_type filters use AND logic."""
    tid = _tid()
    await client.post("/events", json=_event(_uid(), tid, source="web",    event_type="click"))
    await client.post("/events", json=_event(_uid(), tid, source="web",    event_type="view"))
    await client.post("/events", json=_event(_uid(), tid, source="mobile", event_type="click"))

    r = await client.get("/events", params={"tenant_id": tid, "source": "web", "event_type": "click"})
    body = r.json()
    assert body["total"] == 1
    assert body["data"][0]["source"] == "web"
    assert body["data"][0]["event_type"] == "click"


@pytest.mark.asyncio
async def test_list_events_filter_by_time_range(client: AsyncClient):
    """start_time / end_time must narrow results to that window."""
    tid = _tid()
    await client.post("/events", json=_event(_uid(), tid, ts="2024-03-01T09:00:00Z"))  # before
    await client.post("/events", json=_event(_uid(), tid, ts="2024-03-01T10:30:00Z"))  # in range
    await client.post("/events", json=_event(_uid(), tid, ts="2024-03-01T12:00:00Z"))  # after

    r = await client.get("/events", params={
        "tenant_id": tid,
        "start_time": "2024-03-01T10:00:00Z",
        "end_time":   "2024-03-01T11:00:00Z",
    })
    body = r.json()
    assert body["total"] == 1
    assert "10:30" in body["data"][0]["timestamp"]


@pytest.mark.asyncio
async def test_list_events_pagination(client: AsyncClient):
    """limit + offset must page correctly through results."""
    tid = _tid()
    for _ in range(5):
        await client.post("/events", json=_event(_uid(), tid))

    # First page
    r1 = await client.get("/events", params={"tenant_id": tid, "limit": 3, "offset": 0})
    b1 = r1.json()
    assert b1["total"] == 5
    assert len(b1["data"]) == 3

    # Second page
    r2 = await client.get("/events", params={"tenant_id": tid, "limit": 3, "offset": 3})
    b2 = r2.json()
    assert b2["total"] == 5
    assert len(b2["data"]) == 2

    # No overlap between pages
    ids1 = {e["event_id"] for e in b1["data"]}
    ids2 = {e["event_id"] for e in b2["data"]}
    assert ids1.isdisjoint(ids2)


@pytest.mark.asyncio
async def test_list_events_limit_too_large_returns_422(client: AsyncClient):
    """limit is capped at 1000 — exceeding it must return 422."""
    r = await client.get("/events", params={"tenant_id": "t1", "limit": 9999})
    assert r.status_code == 422


# ─────────────────────────────────────────────
# GET /metrics
# ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_aggregates_requires_tenant_id(client: AsyncClient):
    """tenant_id is required — omitting it must return 422."""
    r = await client.get("/metrics")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_get_aggregates_invalid_bucket_size_returns_422(client: AsyncClient):
    """bucket_size must be 'minute' or 'hour' — other values must return 422."""
    r = await client.get("/metrics", params={"tenant_id": "t1", "bucket_size": "second"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_get_aggregates_empty_for_unknown_tenant(client: AsyncClient):
    """A tenant with no aggregates must return an empty data array."""
    r = await client.get("/metrics", params={"tenant_id": "no_such_tenant", "bucket_size": "minute"})
    assert r.status_code == 200
    assert r.json()["data"] == []


@pytest.mark.asyncio
async def test_get_aggregates_grand_total(client: AsyncClient, db: AsyncSession):
    """
    Without source/event_type filters, GET /metrics returns the grand total rows.
    These are the pre-computed rows where source="" and event_type="" in the DB.
    """
    tid = _tid()
    bucket = datetime(2024, 3, 1, 10, 0, tzinfo=timezone.utc)
    await _insert_aggregate_row(db, tid, bucket, "minute", source="", event_type="", count=10)

    r = await client.get("/metrics", params={"tenant_id": tid, "bucket_size": "minute"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["count"] == 10
    # Wildcards returned as None in the API
    assert body["data"][0]["source"] is None
    assert body["data"][0]["event_type"] is None


@pytest.mark.asyncio
async def test_get_aggregates_filtered_by_source(client: AsyncClient, db: AsyncSession):
    """source filter must return the pre-computed (source, all_types) row."""
    tid = _tid()
    bucket = datetime(2024, 3, 1, 10, 0, tzinfo=timezone.utc)
    # Insert both grand total and source-specific rows
    await _insert_aggregate_row(db, tid, bucket, "minute", source="", event_type="", count=5)
    await _insert_aggregate_row(db, tid, bucket, "minute", source="web", event_type="", count=3)

    r = await client.get("/metrics", params={"tenant_id": tid, "bucket_size": "minute", "source": "web"})
    body = r.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["source"] == "web"
    assert body["data"][0]["count"] == 3


@pytest.mark.asyncio
async def test_get_aggregates_filtered_by_event_type(client: AsyncClient, db: AsyncSession):
    """event_type filter must return the pre-computed (all_sources, event_type) row."""
    tid = _tid()
    bucket = datetime(2024, 3, 1, 10, 0, tzinfo=timezone.utc)
    await _insert_aggregate_row(db, tid, bucket, "minute", source="", event_type="click", count=7)

    r = await client.get("/metrics", params={"tenant_id": tid, "bucket_size": "minute", "event_type": "click"})
    body = r.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["event_type"] == "click"
    assert body["data"][0]["count"] == 7


@pytest.mark.asyncio
async def test_get_aggregates_filtered_by_both_dimensions(client: AsyncClient, db: AsyncSession):
    """source + event_type filters must return only the exact (source, event_type) row."""
    tid = _tid()
    bucket = datetime(2024, 3, 1, 10, 0, tzinfo=timezone.utc)
    await _insert_aggregate_row(db, tid, bucket, "minute", source="web",    event_type="click", count=4)
    await _insert_aggregate_row(db, tid, bucket, "minute", source="mobile", event_type="click", count=2)
    await _insert_aggregate_row(db, tid, bucket, "minute", source="",       event_type="",      count=6)

    r = await client.get("/metrics", params={
        "tenant_id": tid, "bucket_size": "minute",
        "source": "web", "event_type": "click"
    })
    body = r.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["source"] == "web"
    assert body["data"][0]["event_type"] == "click"
    assert body["data"][0]["count"] == 4


@pytest.mark.asyncio
async def test_get_aggregates_hour_vs_minute_bucket(client: AsyncClient, db: AsyncSession):
    """bucket_size param must correctly distinguish minute and hour rows."""
    tid = _tid()
    bucket = datetime(2024, 3, 1, 10, 0, tzinfo=timezone.utc)
    await _insert_aggregate_row(db, tid, bucket, "minute", count=5)
    await _insert_aggregate_row(db, tid, bucket, "hour",   count=50)

    r_min = await client.get("/metrics", params={"tenant_id": tid, "bucket_size": "minute"})
    r_hr  = await client.get("/metrics", params={"tenant_id": tid, "bucket_size": "hour"})

    assert r_min.json()["data"][0]["count"] == 5
    assert r_hr.json()["data"][0]["count"] == 50


@pytest.mark.asyncio
async def test_get_aggregates_time_range_filter(client: AsyncClient, db: AsyncSession):
    """start_time / end_time must filter aggregate buckets correctly."""
    tid = _tid()
    b1 = datetime(2024, 3, 1, 9,  0, tzinfo=timezone.utc)  # before range
    b2 = datetime(2024, 3, 1, 10, 0, tzinfo=timezone.utc)  # in range
    b3 = datetime(2024, 3, 1, 11, 0, tzinfo=timezone.utc)  # after range

    for bucket in (b1, b2, b3):
        await _insert_aggregate_row(db, tid, bucket, "hour", count=10)

    r = await client.get("/metrics", params={
        "tenant_id": tid,
        "bucket_size": "hour",
        "start_time": "2024-03-01T10:00:00Z",
        "end_time":   "2024-03-01T10:59:59Z",
    })
    body = r.json()
    assert len(body["data"]) == 1
    assert "10:00" in body["data"][0]["bucket_start"]


@pytest.mark.asyncio
async def test_get_aggregates_multiple_buckets_ordered_asc(client: AsyncClient, db: AsyncSession):
    """Results must be ordered by bucket_start ascending."""
    tid = _tid()
    for minute in (30, 10, 20):
        bucket = datetime(2024, 3, 1, 10, minute, tzinfo=timezone.utc)
        await _insert_aggregate_row(db, tid, bucket, "minute", count=minute)

    r = await client.get("/metrics", params={"tenant_id": tid, "bucket_size": "minute"})
    starts = [row["bucket_start"] for row in r.json()["data"]]
    assert starts == sorted(starts)
