from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.models.event import Event
from app.schemas.event import EventCreate


class EventRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_event(self, event_in: EventCreate) -> None:
        """Inserts a single event. Idempotent via ON CONFLICT DO NOTHING."""
        stmt = insert(Event).values(**event_in.model_dump())
        stmt = stmt.on_conflict_do_nothing(index_elements=["event_id"])
        await self.db.execute(stmt)
        await self.db.commit()

    async def create_bulk_events(self, events_in: List[EventCreate]) -> None:
        """
        Inserts a batch of events in a single executemany statement.
        Far more efficient than N individual inserts — one round trip to the DB.
        Idempotent: duplicates are silently ignored via ON CONFLICT DO NOTHING.
        """
        if not events_in:
            return

        rows = [e.model_dump() for e in events_in]
        stmt = insert(Event).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["event_id"])
        await self.db.execute(stmt)
        await self.db.commit()
