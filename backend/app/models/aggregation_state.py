from sqlalchemy import Column, String, DateTime
from app.database import Base

class AggregationState(Base):
    __tablename__ = "aggregation_state"

    tenant_id = Column(String, primary_key=True, index=True)
    last_processed_created_at = Column(DateTime(timezone=True), nullable=False)
