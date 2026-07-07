from datetime import datetime, timezone
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aggregation_state import AggregationState

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class StateRepository:
    """
    Manages the high-water mark (bookmark) for each tenant.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all_states(self) -> Dict[str, datetime]:
        """
        Returns a dict of {tenant_id: last_processed_created_at} for all tenants.
        Fetched in a single query rather than one per tenant.
        """
        result = await self.db.execute(select(AggregationState))
        rows = result.scalars().all()
        return {row.tenant_id: row.last_processed_created_at for row in rows}

    async def get_last_processed_at(self, tenant_id: str) -> Optional[datetime]:
        """Returns the last processed timestamp for a single tenant."""
        result = await self.db.execute(
            select(AggregationState).where(AggregationState.tenant_id == tenant_id)
        )
        state = result.scalar_one_or_none()
        return state.last_processed_created_at if state else None

    async def upsert_state(self, tenant_id: str, last_processed_at: datetime) -> None:
        """Moves the bookmark forward for a tenant."""
        stmt = insert(AggregationState).values(
            tenant_id=tenant_id,
            last_processed_created_at=last_processed_at
        ).on_conflict_do_update(
            index_elements=["tenant_id"],
            set_={"last_processed_created_at": last_processed_at}
        )
        await self.db.execute(stmt)
