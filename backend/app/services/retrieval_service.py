from datetime import datetime
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.retrieval_repository import RetrievalRepository
from app.schemas.response import (
    AggregateResponse,
    AggregatesResponse,
    EventResponse,
    PaginatedEventsResponse,
)


class RetrievalService:
    """
    Business logic for reading events and aggregates.
    Maps DB models → response schemas.
    """

    def __init__(self, db: AsyncSession):
        self.repo = RetrievalRepository(db)

    async def get_events(
        self,
        tenant_id: str,
        source: Optional[str],
        event_type: Optional[str],
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        limit: int,
        offset: int,
    ) -> PaginatedEventsResponse:
        total, events = await self.repo.get_events(
            tenant_id=tenant_id,
            source=source,
            event_type=event_type,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )
        return PaginatedEventsResponse(
            total=total,
            limit=limit,
            offset=offset,
            data=[EventResponse.model_validate(e) for e in events],
        )

    async def get_aggregates(
        self,
        tenant_id: str,
        bucket_size: str,
        source: Optional[str],
        event_type: Optional[str],
        start_time: Optional[datetime],
        end_time: Optional[datetime],
    ) -> AggregatesResponse:
        aggregates = await self.repo.get_aggregates(
            tenant_id=tenant_id,
            bucket_size=bucket_size,
            source=source,
            event_type=event_type,
            start_time=start_time,
            end_time=end_time,
        )

        # Map DB empty string "" back to None for clean API responses
        rows = []
        for agg in aggregates:
            rows.append(AggregateResponse(
                tenant_id=agg.tenant_id,
                bucket_start=agg.bucket_start,
                bucket_size=agg.bucket_size,
                source=agg.source if agg.source != "" else None,
                event_type=agg.event_type if agg.event_type != "" else None,
                count=agg.count,
                first_seen=agg.first_seen,
                last_seen=agg.last_seen,
            ))

        return AggregatesResponse(
            tenant_id=tenant_id,
            bucket_size=bucket_size,
            data=rows,
        )
