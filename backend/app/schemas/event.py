from datetime import datetime, timezone
from typing import Any, Dict
from pydantic import BaseModel, Field, field_validator

class EventBase(BaseModel):
    event_id: str = Field(..., description="Globally unique identifier for the event")
    tenant_id: str = Field(..., description="Identifier for the tenant")
    source: str = Field(..., description="Source of the event (e.g. web, mobile, device)")
    event_type: str = Field(..., description="Type of the event (e.g. click, view, error)")
    timestamp: datetime = Field(..., description="UTC datetime of the event")
    payload: Dict[str, Any] = Field(..., description="JSON object containing event details")

    @field_validator("timestamp")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)

class EventCreate(EventBase):
    pass

class EventResponse(EventBase):
    created_at: datetime

    model_config = {"from_attributes": True}

