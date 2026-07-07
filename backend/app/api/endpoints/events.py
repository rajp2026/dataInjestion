from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.event import EventCreate
from app.services.event_service import EventService

router = APIRouter()

@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
async def create_event(event: EventCreate, db: AsyncSession = Depends(get_db)):
    event_service = EventService(db)
    await event_service.process_event(event)
    return {"status": "accepted"}
