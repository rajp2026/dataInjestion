from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EventResponse(BaseModel):
    event_id: str
    tenant_id: str
    source: str
    event_type: str
    timestamp: datetime
    payload: Dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class AggregateResponse(BaseModel):
    tenant_id: str
    bucket_start: datetime
    bucket_size: str
    source: Optional[str] = None     # None means "all sources"
    event_type: Optional[str] = None # None means "all event types"
    count: int
    first_seen: datetime
    last_seen: datetime

    model_config = {"from_attributes": True}


class PaginatedEventsResponse(BaseModel):
    total: int
    limit: int
    offset: int
    data: List[EventResponse]


class AggregatesResponse(BaseModel):
    tenant_id: str
    bucket_size: str
    data: List[AggregateResponse]
