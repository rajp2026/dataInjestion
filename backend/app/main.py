from fastapi import FastAPI
from app.api import api_router

app = FastAPI(title="Data Ingestion Service")

app.include_router(api_router)
