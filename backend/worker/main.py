import asyncio
import logging
import sys

from app.database import AsyncSessionLocal
from worker.aggregator import AggregationService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("worker")

# How often the worker wakes up to check for new events (in seconds)
POLL_INTERVAL_SECONDS = 5


async def run_worker() -> None:
    logger.info("=" * 50)
    logger.info("Aggregation Worker started.")
    logger.info(f"Polling every {POLL_INTERVAL_SECONDS}s for new events.")
    logger.info("=" * 50)

    while True:
        try:
            async with AsyncSessionLocal() as db:
                service = AggregationService(db)
                await service.run_cycle()
        except Exception as exc:
            # Log the error but keep the worker alive — never crash on a transient error
            logger.error(f"Error during aggregation cycle: {exc}", exc_info=True)

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(run_worker())
