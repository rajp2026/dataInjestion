import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from worker.models import AggregateRow
from worker.repositories.aggregate_repository import AggregateRepository
from worker.repositories.state_repository import StateRepository

logger = logging.getLogger(__name__)

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

BATCH_SIZE = 1000

# Bucket granularities: (name, size_in_minutes)
BUCKET_CONFIGS = [
    ("minute", 1),
    ("hour", 60),
]

# FIX #5: Use None instead of "" for wildcard dimensions — more type-safe and self-documenting
DIMENSION_WILDCARDS: List[Tuple[Optional[str], Optional[str]]] = [
    # (source,        event_type)
    ("__source__",   "__event_type__"),  # exact match — replaced per event
    ("__source__",   None),             # all types for this source
    (None,           "__event_type__"), # all sources for this type
    (None,           None),             # grand total
]


def _truncate_to_bucket(dt: datetime, bucket_minutes: int) -> datetime:
    """Truncates a datetime to the nearest bucket boundary."""
    total_minutes = dt.hour * 60 + dt.minute
    bucket_start_minutes = (total_minutes // bucket_minutes) * bucket_minutes
    return dt.replace(
        hour=bucket_start_minutes // 60,
        minute=bucket_start_minutes % 60,
        second=0,
        microsecond=0,
    )


def _build_aggregate_rows(events: List[Event]) -> List[AggregateRow]:
   
    # Key: (tenant_id, bucket_start, bucket_size, source|None, event_type|None)
    buckets: Dict[tuple, AggregateRow] = {}

    for event in events:
        ts = event.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        for bucket_size, bucket_minutes in BUCKET_CONFIGS:
            bucket_start = _truncate_to_bucket(ts, bucket_minutes)

            # FIX #5: Use None for wildcard dimensions
            dimension_combos: List[Tuple[Optional[str], Optional[str]]] = [
                (event.source, event.event_type),
                (event.source, None),
                (None, event.event_type),
                (None, None),
            ]

            for source, event_type in dimension_combos:
                key = (event.tenant_id, bucket_start, bucket_size, source, event_type)

                if key in buckets:
                    row = buckets[key]
                    row.count += 1
                    if ts < row.first_seen:
                        row.first_seen = ts
                    if ts > row.last_seen:
                        row.last_seen = ts
                else:
                    buckets[key] = AggregateRow(
                        tenant_id=event.tenant_id,
                        bucket_start=bucket_start,
                        bucket_size=bucket_size,
                        source=source,
                        event_type=event_type,
                        count=1,
                        first_seen=ts,
                        last_seen=ts,
                    )

    return list(buckets.values())


def _trim_tie_events(events: List[Event]) -> List[Event]:
    if len(events) < BATCH_SIZE:
        return events  # Batch was not full — no tie risk

    last_ts = events[-1].created_at
    trimmed = [e for e in events if e.created_at < last_ts]

    if not trimmed:
        # All events share the same timestamp — can't trim, process all
        logger.warning(
            f"All {len(events)} events in batch share created_at={last_ts}. "
            "Processing all; watermark tie unavoidable."
        )
        return events

    logger.debug(
        f"Trimmed {len(events) - len(trimmed)} tail events at created_at={last_ts} "
        "to avoid watermark tie."
    )
    return trimmed


class AggregationService:

    def __init__(self, db: AsyncSession):
        self.agg_repo = AggregateRepository(db)
        self.state_repo = StateRepository(db)
        self.db = db

    async def run_cycle(self) -> None:
        """Runs one full aggregation cycle."""

        # FIX #1: Load all known watermarks in ONE query
        all_states = await self.state_repo.get_all_states()
        known_watermarks = list(all_states.values())
        global_since = min(known_watermarks) if known_watermarks else _EPOCH

        # FIX #1: Single global query across all tenants
        events = await self.agg_repo.fetch_unprocessed_events_global(
            after=global_since,
            batch_size=BATCH_SIZE,
        )

        if not events:
            logger.debug("No new events. Skipping cycle.")
            return

        # FIX #2: Handle watermark ties by trimming tail events
        events = _trim_tie_events(events)

        # Group events by tenant in Python — no extra DB queries
        by_tenant: Dict[str, List[Event]] = defaultdict(list)
        for event in events:
            by_tenant[event.tenant_id].append(event)

        all_rows: List[AggregateRow] = []
        new_watermarks: Dict[str, datetime] = {}

        for tenant_id, tenant_events in by_tenant.items():
            # Per-tenant watermark filter: skip events already processed
            tenant_wm = all_states.get(tenant_id) or _EPOCH
            new_events = [e for e in tenant_events if e.created_at > tenant_wm]

            if not new_events:
                continue

            logger.info(f"[{tenant_id}] Aggregating {len(new_events)} new events.")

            rows = _build_aggregate_rows(new_events)
            all_rows.extend(rows)

            wm = max(e.created_at for e in new_events)
            if wm.tzinfo is None:
                wm = wm.replace(tzinfo=timezone.utc)
            new_watermarks[tenant_id] = wm

        # FIX #6: Wrap UPSERT + state update in a single transaction with rollback
        try:
            # Bulk upsert all aggregate rows across all tenants
            await self.agg_repo.bulk_upsert_aggregates(
                [row.to_db_dict() for row in all_rows]
            )

            # Update all tenant watermarks
            for tenant_id, wm in new_watermarks.items():
                await self.state_repo.upsert_state(tenant_id, wm)
                logger.info(f"[{tenant_id}] Watermark advanced to {wm}.")

            # FIX #3: Single commit for the entire cycle
            await self.db.commit()

        except Exception:
            await self.db.rollback()
            logger.error("Cycle failed — rolled back all changes.", exc_info=True)
            raise
