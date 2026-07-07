from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.event import EventCreate
from app.repositories.event_repository import EventRepository

class EventService:
    def __init__(self, db: AsyncSession):
        self.repository = EventRepository(db)

    async def process_event(self, event_in: EventCreate) -> None:
        # Business logic goes here (e.g. validation, transformations)
        # For now, it simply delegates to the repository for UPSERT
        await self.repository.create_event(event_in)
