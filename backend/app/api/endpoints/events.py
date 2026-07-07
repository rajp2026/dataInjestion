from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.event import EventCreate
from app.services.event_service import EventService

router = APIRouter()


@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
async def create_event(event: EventCreate, db: AsyncSession = Depends(get_db)):
    """
    Ingest a single event.
    Idempotent: duplicate event_ids are safely ignored.
    """
    service = EventService(db)
    await service.process_event(event)
    return {"status": "accepted"}


@router.post("/events/bulk", status_code=status.HTTP_202_ACCEPTED)
async def create_events_bulk(events: List[EventCreate], db: AsyncSession = Depends(get_db)):
    """
    Ingest a batch of events in a single request.
    Designed for clients that buffer events locally (mobile apps, analytics SDKs).
    Each event is idempotent — duplicates are safely ignored.
    Max batch size enforced at the Pydantic validation layer.
    """
    service = EventService(db)
    await service.process_bulk_events(events)
    return {"status": "accepted", "received": len(events)}
