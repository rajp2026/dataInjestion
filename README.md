# Data Ingestion & Aggregation Service

A production-grade async backend service built with **FastAPI**, **PostgreSQL**, and **SQLAlchemy 2.0** that ingests events, aggregates them in the background, and exposes fast read APIs.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Clients                              │
│          (Mobile Apps, Web SDKs, Webhooks, Services)        │
└─────────────────────────┬───────────────────────────────────┘
                          │
                    POST /events
                POST /events/bulk
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                   FastAPI (API Server)                       │
│         api/ → services/ → repositories/ → PostgreSQL       │
│                                                             │
│   • Idempotent inserts (ON CONFLICT DO NOTHING)             │
│   • Validates with Pydantic                                 │
│   • Async I/O via asyncpg                                   │
└──────────────────────────┬──────────────────────────────────┘
                           │ writes raw events
                ┌──────────▼──────────┐
                │    events table     │  ← raw event store
                └──────────┬──────────┘
                           │ reads (High-Water Mark)
┌──────────────────────────▼──────────────────────────────────┐
│              Aggregation Worker (separate process)          │
│                                                             │
│  Every 5s:                                                  │
│  1. Read last processed timestamp (aggregation_state)       │
│  2. Fetch new events in a single global query               │
│  3. Compute all dimension combos in Python memory           │
│  4. Bulk UPSERT into aggregates table                       │
│  5. Advance high-water mark → commit (1 commit/cycle)       │
└──────────────────────────┬──────────────────────────────────┘
                           │ writes pre-computed counts
            ┌──────────────▼──────────────┐
            │       aggregates table       │  ← fast read store
            └──────────────┬──────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                   FastAPI (API Server)                       │
│        GET /events  →  GET /metrics                      │
└─────────────────────────────────────────────────────────────┘
```

### Three Decoupled Tables

| Table | Purpose | Who Writes | Who Reads |
|-------|---------|-----------|----------|
| `events` | Raw event store | API Server | Worker |
| `aggregates` | Pre-computed counts by time bucket + dimensions | Worker | API Server |
| `aggregation_state` | High-water mark bookmark per tenant | Worker | Worker |

> **Why decoupled?** No foreign keys between tables means the API can insert at full speed without lock contention. The worker processes data asynchronously. Historical events can be archived without breaking aggregate queries.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Framework | FastAPI |
| Database | PostgreSQL |
| Async ORM | SQLAlchemy 2.0 (async) |
| DB Driver | asyncpg |
| Migrations | Alembic |
| Validation | Pydantic v2 |
| Testing | pytest + pytest-asyncio + httpx |

---

## Project Structure

```
backend/
├── app/                        # FastAPI application
│   ├── api/
│   │   ├── __init__.py         # API router aggregator
│   │   └── endpoints/
│   │       ├── events.py       # POST /events, POST /events/bulk
│   │       └── retrieval.py    # GET /events, GET /metrics
│   ├── models/
│   │   ├── event.py            # SQLAlchemy Event model
│   │   ├── aggregate.py        # SQLAlchemy Aggregate model
│   │   └── aggregation_state.py
│   ├── repositories/
│   │   ├── event_repository.py      # Idempotent inserts
│   │   └── retrieval_repository.py  # Paginated reads
│   ├── services/
│   │   ├── event_service.py         # Ingestion business logic
│   │   └── retrieval_service.py     # Query orchestration
│   ├── schemas/
│   │   ├── event.py                 # Pydantic input schemas
│   │   └── response.py              # Pydantic output schemas
│   ├── database.py             # Async engine + session factory
│   └── main.py                 # FastAPI app entry point
│
├── worker/                     # Aggregation worker (separate process)
│   ├── main.py                 # Entry point — infinite polling loop
│   ├── aggregator.py           # Core aggregation logic
│   ├── models.py               # AggregateRow dataclass
│   └── repositories/
│       ├── aggregate_repository.py  # Fetch events, bulk upsert
│       └── state_repository.py      # High-water mark management
│
├── alembic/                    # Database migrations
│   └── versions/
│       └── bb29504c6d8b_initial_schema.py
│
├── tests/
│   ├── conftest.py             # Pytest fixtures (NullPool engine, dependency override)
│   ├── api/
│   │   ├── test_events.py      # Ingestion endpoint tests
│   │   └── test_retrieval.py   # Retrieval endpoint tests
│   └── worker/
│       └── test_aggregator.py  # Pure unit tests (no DB)
│
├── alembic.ini
└── pytest.ini
```

---

## Setup

### Prerequisites

- Python 3.10+
- PostgreSQL running locally

### 1. Clone & enter the backend directory

```bash
git clone https://github.com/rajp2026/dataInjestion.git
cd dataInjestion/backend
```

### 2. Create a virtual environment

```bash
python -m venv venv

# Windows
.\venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install fastapi "uvicorn[standard]" sqlalchemy asyncpg pydantic \
            pytest pytest-asyncio httpx alembic python-dotenv
```

### 4. Configure the database URL

Open `app/database.py` and update the connection string with your PostgreSQL credentials:

```python
SQLALCHEMY_DATABASE_URL = "postgresql+asyncpg://<user>:<password>@localhost:5432/<dbname>"
```

### 5. Run Alembic migrations

```bash
.\venv\Scripts\alembic upgrade head   # Windows
alembic upgrade head                   # macOS/Linux
```

This creates the `events`, `aggregates`, and `aggregation_state` tables.

---

## Running the Service

The API server and the aggregation worker run as **two independent processes**. Open two separate terminals inside `backend/`.

### Terminal 1 — API Server

```bash
.\venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Terminal 2 — Aggregation Worker

```bash
.\venv\Scripts\python -m worker.main
```

Worker output:
```
Aggregation Worker started.
Polling every 5s for new events.
[tenant_1] Aggregating 42 new events.
[tenant_1] Watermark advanced to 2024-03-01T10:05:33+00:00.
```

---

## API Reference

Interactive docs available at: **`http://127.0.0.1:8000/docs`**

---

### POST `/events` — Ingest a single event

```bash
curl -X POST http://127.0.0.1:8000/events \
  -H "Content-Type: application/json" \
  -d '{
    "event_id":   "evt_unique_001",
    "tenant_id":  "tenant_1",
    "source":     "web",
    "event_type": "click",
    "timestamp":  "2024-03-01T10:00:00Z",
    "payload":    {"user_id": 42, "page": "/home"}
  }'
```

**Response** `202 Accepted`
```json
{ "status": "accepted" }
```

> **Idempotent**: sending the same `event_id` twice will return `202` but only store one row.

---

### POST `/events/bulk` — Ingest a batch of events

```bash
curl -X POST http://127.0.0.1:8000/events/bulk \
  -H "Content-Type: application/json" \
  -d '[
    {"event_id": "evt_001", "tenant_id": "tenant_1", "source": "web",    "event_type": "click", "timestamp": "2024-03-01T10:00:10Z", "payload": {}},
    {"event_id": "evt_002", "tenant_id": "tenant_1", "source": "mobile", "event_type": "view",  "timestamp": "2024-03-01T10:00:20Z", "payload": {}},
    {"event_id": "evt_003", "tenant_id": "tenant_1", "source": "web",    "event_type": "click", "timestamp": "2024-03-01T10:01:05Z", "payload": {}}
  ]'
```

**Response** `202 Accepted`
```json
{ "status": "accepted", "received": 3 }
```

---

### GET `/events` — Query raw events

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tenant_id` | string | ✅ | Tenant to query |
| `source` | string | ❌ | Filter by source (e.g. `web`, `mobile`) |
| `event_type` | string | ❌ | Filter by event type (e.g. `click`, `view`) |
| `start_time` | datetime | ❌ | Events at or after this UTC timestamp |
| `end_time` | datetime | ❌ | Events at or before this UTC timestamp |
| `limit` | int | ❌ | Max results (1–1000, default 100) |
| `offset` | int | ❌ | Skip N results (default 0) |

```bash
# All events for a tenant
curl "http://127.0.0.1:8000/events?tenant_id=tenant_1"

# Filter by source and type
curl "http://127.0.0.1:8000/events?tenant_id=tenant_1&source=web&event_type=click"

# Time range + pagination
curl "http://127.0.0.1:8000/events?tenant_id=tenant_1&start_time=2024-03-01T10:00:00Z&end_time=2024-03-01T11:00:00Z&limit=50&offset=0"
```

**Response** `200 OK`
```json
{
  "total": 42,
  "limit": 100,
  "offset": 0,
  "data": [
    {
      "event_id": "evt_001",
      "tenant_id": "tenant_1",
      "source": "web",
      "event_type": "click",
      "timestamp": "2024-03-01T10:00:10Z",
      "payload": {},
      "created_at": "2024-03-01T10:00:11Z"
    }
  ]
}
```

---

### GET `/metrics` — Query pre-computed metrics

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tenant_id` | string | ✅ | Tenant to query |
| `bucket_size` | `minute` \| `hour` | ❌ | Granularity (default `minute`) |
| `source` | string | ❌ | Filter by source — **omit for totals across all sources** |
| `event_type` | string | ❌ | Filter by event type — **omit for totals across all types** |
| `start_time` | datetime | ❌ | Buckets at or after this timestamp |
| `end_time` | datetime | ❌ | Buckets at or before this timestamp |

```bash
# Grand total per minute bucket (no filters)
curl "http://127.0.0.1:8000/metrics?tenant_id=tenant_1&bucket_size=minute"

# Per hour, only web events
curl "http://127.0.0.1:8000/metrics?tenant_id=tenant_1&bucket_size=hour&source=web"

# Specific dimension: web clicks per minute
curl "http://127.0.0.1:8000/metrics?tenant_id=tenant_1&bucket_size=minute&source=web&event_type=click"

# Time range
curl "http://127.0.0.1:8000/metrics?tenant_id=tenant_1&bucket_size=hour&start_time=2024-03-01T00:00:00Z&end_time=2024-03-01T23:59:59Z"
```

**Response** `200 OK`
```json
{
  "tenant_id": "tenant_1",
  "bucket_size": "minute",
  "data": [
    {
      "tenant_id":   "tenant_1",
      "bucket_start": "2024-03-01T10:00:00Z",
      "bucket_size": "minute",
      "source":      null,
      "event_type":  null,
      "count":       7,
      "first_seen":  "2024-03-01T10:00:05Z",
      "last_seen":   "2024-03-01T10:00:55Z"
    }
  ]
}
```

> `source: null` and `event_type: null` means the row is a **grand total** across all sources/types.

---

## Running Tests

```bash
.\venv\Scripts\python -m pytest tests/ -v
```

```
collected 40 items

tests/api/test_events.py::test_single_event_returns_202              PASSED
tests/api/test_events.py::test_single_event_persisted_in_db          PASSED
tests/api/test_events.py::test_single_event_idempotency              PASSED
tests/api/test_events.py::test_single_event_missing_required_field   PASSED
tests/api/test_events.py::test_bulk_insert_returns_202_with_count    PASSED
tests/api/test_events.py::test_bulk_insert_deduplicates_within_batch PASSED
... (11 total)

tests/api/test_retrieval.py::test_list_events_filter_by_source       PASSED
tests/api/test_retrieval.py::test_get_aggregates_grand_total         PASSED
tests/api/test_retrieval.py::test_get_aggregates_filtered_by_source  PASSED
... (19 total)

tests/worker/test_aggregator.py::TestBuildAggregateRows (10 tests)   PASSED
tests/worker/test_aggregator.py::TestTrimTieEvents (3 tests)         PASSED

======================== 40 passed in 13.44s ============================
```

### Test Design

| Test File | Scope | DB Required |
|-----------|-------|------------|
| `test_events.py` | Ingestion endpoints | ✅ Real PostgreSQL |
| `test_retrieval.py` | Retrieval endpoints | ✅ Real PostgreSQL |
| `test_aggregator.py` | Worker pure functions | ❌ No DB (unit tests) |

> Tests use a `NullPool` engine with FastAPI dependency override — no server spin-up needed.
> Each test uses a unique `tenant_id`/`event_id` (UUID-based) for full isolation without truncating tables.

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Decoupled tables** | No foreign keys → maximum ingestion throughput |
| **High-Water Mark** | Worker tracks progress via `aggregation_state` — never marks events as "processed" |
| **Combinatorial buckets** | Pre-compute all 4 dimension combinations per event so any filter is O(1) at read time |
| **Single global query** | Worker uses 1 query per cycle instead of N per-tenant queries |
| **Tail trimming** | Prevents watermark ties when events share the same `created_at` |
| **Single commit per cycle** | Reduces PostgreSQL WAL flushes from N→1 |
| **Atomic transaction** | UPSERT + watermark update in one transaction — prevents double-counting on failure |
| **NullPool for tests** | Avoids asyncpg connection conflicts between the app and test verification queries |
