from fastapi import APIRouter
from .endpoints.events import router as events_router
from .endpoints.retrieval import router as retrieval_router
from .endpoints.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(events_router, tags=["ingestion"])
api_router.include_router(retrieval_router, tags=["retrieval"])
