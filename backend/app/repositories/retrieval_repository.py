from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.models.aggregate import Aggregate


class RetrievalRepository:
    """
    Read-only data access layer for events and aggregates.
    All queries are scoped by tenant_id for strict multi-tenancy.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─────────────────────────────
    # Raw Events
    # ─────────────────────────────

    async def get_events(
        self,
        tenant_id: str,
        source: Optional[str] = None,
        event_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[int, List[Event]]:
        """
        Returns (total_count, paginated_events) for a tenant.
        Filters are all optional and additive (AND logic).
        Uses the same query for count and data to keep them consistent.
        """
        filters = [Event.tenant_id == tenant_id]

        if source:
            filters.append(Event.source == source)
        if event_type:
            filters.append(Event.event_type == event_type)
        if start_time:
            filters.append(Event.timestamp >= start_time)
        if end_time:
            filters.append(Event.timestamp <= end_time)

        where_clause = and_(*filters)

        # Count query
        count_result = await self.db.scalar(
            select(func.count()).select_from(Event).where(where_clause)
        )
        total = count_result or 0

        # Data query — ordered by timestamp descending (newest first)
        result = await self.db.execute(
            select(Event)
            .where(where_clause)
            .order_by(Event.timestamp.desc())
            .limit(limit)
            .offset(offset)
        )
        events = result.scalars().all()

        return total, list(events)

    # ─────────────────────────────
    # Aggregates
    # ─────────────────────────────

    async def get_aggregates(
        self,
        tenant_id: str,
        bucket_size: str,
        source: Optional[str] = None,
        event_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Aggregate]:
        """
        Returns pre-computed aggregates for a tenant.

        Key Design: source/event_type map to the DB's "" wildcard sentinel.
        - No source filter   → query source=""   (grand total across all sources)
        - source="web"       → query source="web" (only web events)
        This matches how the worker pre-computed the combinatorial buckets.
        """
        # Map None → "" for wildcard lookup in the DB
        db_source = source if source is not None else ""
        db_event_type = event_type if event_type is not None else ""

        filters = [
            Aggregate.tenant_id == tenant_id,
            Aggregate.bucket_size == bucket_size,
            Aggregate.source == db_source,
            Aggregate.event_type == db_event_type,
        ]

        if start_time:
            filters.append(Aggregate.bucket_start >= start_time)
        if end_time:
            filters.append(Aggregate.bucket_start <= end_time)

        result = await self.db.execute(
            select(Aggregate)
            .where(and_(*filters))
            .order_by(Aggregate.bucket_start.asc())
        )
        return result.scalars().all()
