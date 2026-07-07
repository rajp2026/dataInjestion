from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class AggregateRow:
    tenant_id: str
    bucket_start: datetime
    bucket_size: str
    source: Optional[str]       # None = "all sources" wildcard
    event_type: Optional[str]   # None = "all types" wildcard
    count: int
    first_seen: datetime
    last_seen: datetime

    def to_db_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "bucket_start": self.bucket_start,
            "bucket_size": self.bucket_size,
            "source": self.source if self.source is not None else "",
            "event_type": self.event_type if self.event_type is not None else "",
            "count": self.count,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }
