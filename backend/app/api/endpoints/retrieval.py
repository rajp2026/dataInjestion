from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.response import AggregatesResponse, PaginatedEventsResponse
from app.services.retrieval_service import RetrievalService

router = APIRouter()


@router.get("/events", response_model=PaginatedEventsResponse)
async def list_events(
    tenant_id: str = Query(..., description="Tenant identifier (required)"),
    source: Optional[str] = Query(None, description="Filter by source (e.g. web, mobile)"),
    event_type: Optional[str] = Query(None, description="Filter by event type (e.g. click, view)"),
    start_time: Optional[datetime] = Query(None, description="Filter events at or after this UTC timestamp"),
    end_time: Optional[datetime] = Query(None, description="Filter events at or before this UTC timestamp"),
    limit: int = Query(100, ge=1, le=1000, description="Max number of events to return"),
    offset: int = Query(0, ge=0, description="Number of events to skip (for pagination)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Query raw ingested events for a tenant.

    Supports optional filtering by source, event_type, and time range.
    Results are ordered by event timestamp (newest first) with limit/offset pagination.
    """
    service = RetrievalService(db)
    return await service.get_events(
        tenant_id=tenant_id,
        source=source,
        event_type=event_type,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )


@router.get("/metrics", response_model=AggregatesResponse)
async def get_aggregates(
    tenant_id: str = Query(..., description="Tenant identifier (required)"),
    bucket_size: Literal["minute", "hour"] = Query("minute", description="Time bucket granularity"),
    source: Optional[str] = Query(None, description="Filter by source. Omit for totals across all sources."),
    event_type: Optional[str] = Query(None, description="Filter by event type. Omit for totals across all types."),
    start_time: Optional[datetime] = Query(None, description="Return buckets whose bucket_start falls at or after this UTC timestamp"),
    end_time: Optional[datetime] = Query(None, description="Return buckets whose bucket_start falls at or before this UTC timestamp"),
    db: AsyncSession = Depends(get_db),
):
    """
    Query pre-computed aggregated metrics for a tenant.

    """
    service = RetrievalService(db)
    return await service.get_aggregates(
        tenant_id=tenant_id,
        bucket_size=bucket_size,
        source=source,
        event_type=event_type,
        start_time=start_time,
        end_time=end_time,
    )
