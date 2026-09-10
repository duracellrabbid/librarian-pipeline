"""IngestionJob entity model representing background processing tasks."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, DateTime
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


class BatchJobStatus(StrEnum):
    """Lifecycle state machine stages for a batch ingestion job."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    PARTIALLY_FAILED = "PARTIALLY_FAILED"
    FAILED = "FAILED"


class BatchIngestionJob(SQLModel, table=True):
    """Batch ingestion job tracking aggregate status, counts, and skipped document details."""

    __tablename__ = "batch_ingestion_jobs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    status: str = Field(default=BatchJobStatus.PENDING.value, index=True, nullable=False)
    total_count: int = Field(default=0, ge=0, nullable=False)
    accepted_count: int = Field(default=0, ge=0, nullable=False)
    skipped_count: int = Field(default=0, ge=0, nullable=False)
    skipped_details: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False, server_default="[]"),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
    finished_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
    )

    jobs: list["IngestionJob"] = Relationship(
        back_populates="batch",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class IngestionJob(SQLModel, table=True):
    """Background ingestion job tracking progress, state transitions, and errors."""

    __tablename__ = "ingestion_jobs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    batch_id: UUID | None = Field(
        default=None,
        foreign_key="batch_ingestion_jobs.id",
        index=True,
        nullable=True,
    )
    document_id: UUID = Field(foreign_key="documents.id", index=True, nullable=False)
    status: str = Field(default=JobStatus.PENDING.value, index=True, nullable=False)
    error_message: str | None = Field(default=None, nullable=True)
    progress_percentage: int = Field(default=0, ge=0, le=100, nullable=False)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
    finished_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
    )

    document: Optional["Document"] = Relationship(back_populates="jobs")
    batch: Optional["BatchIngestionJob"] = Relationship(back_populates="jobs")
