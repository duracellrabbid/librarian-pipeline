"""REST API endpoints for document ingestion, status tracking, checking, and deletion."""

from fastapi import APIRouter

router = APIRouter(prefix="/documents", tags=["documents"])
