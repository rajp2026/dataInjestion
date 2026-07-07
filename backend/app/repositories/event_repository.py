from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from app.models.event import Event
from app.schemas.event import EventCreate

class EventRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_event(self, event_in: EventCreate) -> None:
        event_data = event_in.model_dump()
        
        stmt = insert(Event).values(**event_data)
        stmt = stmt.on_conflict_do_nothing(index_elements=['event_id'])
        
        await self.db.execute(stmt)
        await self.db.commit()
