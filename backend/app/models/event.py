from sqlalchemy import Column, String, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.database import Base

class Event(Base):
    __tablename__ = "events"

    event_id = Column(String, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False)
    source = Column(String, nullable=False)
    event_type = Column(String, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    payload = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_events_tenant_timestamp", "tenant_id", "timestamp"),
        Index("ix_events_tenant_created_at", "tenant_id", "created_at"),
    )
