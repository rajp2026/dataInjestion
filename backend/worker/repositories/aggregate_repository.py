from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, distinct, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.event import Event
from app.models.aggregate import Aggregate

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class AggregateRepository:
    """
    Handles all database reads for raw events and writes for pre-computed aggregates.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def fetch_global_min_watermark(self, known_watermarks: List[datetime]) -> datetime:
        """
        Returns the global floor for the worker query.
        If there are no known watermarks (no tenants processed yet), returns EPOCH.
        This ensures new tenants with no state entry are always caught.
        """
        if not known_watermarks:
            return _EPOCH
        return min(known_watermarks)

    async def fetch_unprocessed_events_global(
        self,
        after: datetime,
        batch_size: int = 1000,
    ) -> List[Event]:
        """
        FIX #1: Single global query instead of N per-tenant queries.

        Fetches a batch of raw events across ALL tenants where created_at > after,
        oldest first. Grouping by tenant is done in Python, not via N DB round trips.
        """
        result = await self.db.execute(
            select(Event)
            .where(Event.created_at > after)
            .order_by(Event.created_at.asc())
            .limit(batch_size)
        )
        return result.scalars().all()

    async def bulk_upsert_aggregates(self, rows: List[dict]) -> None:
        """
        Bulk UPSERTs pre-computed aggregate rows.
        ON CONFLICT: safely adds the new count to the existing count.
        """
        if not rows:
            return

        stmt = pg_insert(Aggregate).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_aggregate_dimensions",
            set_={
                "count": Aggregate.count + stmt.excluded.count,
                "last_seen": stmt.excluded.last_seen,
            }
        )
        await self.db.execute(stmt)
