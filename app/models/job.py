"""IngestionJob entity model representing background processing tasks."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.document import Document


def utc_now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(UTC)


class JobStatus(StrEnum):
    """Lifecycle state machine stages for an ingestion job."""

    PENDING = "PENDING"
    SCRAPING = "SCRAPING"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"


class IngestionJob(SQLModel, table=True):
    """Background ingestion job tracking progress, state transitions, and errors."""

    __tablename__ = "ingestion_jobs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    document_id: UUID = Field(foreign_key="documents.id", index=True, nullable=False)
    status: str = Field(default=JobStatus.PENDING.value, index=True, nullable=False)
    error_message: str | None = Field(default=None, nullable=True)
    progress_percentage: int = Field(default=0, ge=0, le=100, nullable=False)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    finished_at: datetime | None = Field(default=None, nullable=True)

    document: Optional["Document"] = Relationship(back_populates="jobs")
