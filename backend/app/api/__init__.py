from fastapi import APIRouter
from .endpoints.events import router as events_router

api_router = APIRouter()
api_router.include_router(events_router, tags=["events"])
