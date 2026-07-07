from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.event import EventCreate
from app.repositories.event_repository import EventRepository


class EventService:
    def __init__(self, db: AsyncSession):
        self.repository = EventRepository(db)

    async def process_event(self, event_in: EventCreate) -> None:
        """Processes a single event — delegates to repository for idempotent insert."""
        await self.repository.create_event(event_in)

    async def process_bulk_events(self, events_in: List[EventCreate]) -> None:
        """
        Processes a batch of events in a single DB round trip.
        Business logic can be applied here before persisting (e.g. filtering, enrichment).
        """
        await self.repository.create_bulk_events(events_in)
