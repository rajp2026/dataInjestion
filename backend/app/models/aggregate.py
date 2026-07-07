from sqlalchemy import Column, String, Integer, DateTime, UniqueConstraint
from app.database import Base

class Aggregate(Base):
    __tablename__ = "aggregates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, nullable=False)
    bucket_start = Column(DateTime(timezone=True), nullable=False)
    bucket_size = Column(String, nullable=False) # 'minute' or 'hour'
    source = Column(String, default="", nullable=False)
    event_type = Column(String, default="", nullable=False)
    
    count = Column(Integer, default=0, nullable=False)
    first_seen = Column(DateTime(timezone=True), nullable=False)
    last_seen = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "bucket_start", "bucket_size", "source", "event_type",
            name="uq_aggregate_dimensions"
        ),
    )
