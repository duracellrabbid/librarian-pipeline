"""Central router aggregator for API v1."""

from fastapi import APIRouter

from app.api.v1.endpoints import documents

api_v1_router = APIRouter()
api_v1_router.include_router(documents.router)
