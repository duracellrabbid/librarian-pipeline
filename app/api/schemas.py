"""Request and response Pydantic schemas for the REST API."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.models.job import JobStatus


class IngestRequest(BaseModel):
    """Payload for submitting a new document ingestion request."""

    model_config = ConfigDict(from_attributes=True)

    url: HttpUrl = Field(description="Target web URL to scrape and index")
    title: str | None = Field(default=None, description="Optional document title or label")
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional metadata associated with the document",
    )


class IngestResponse(BaseModel):
    """Response returned upon successful document ingestion submission."""

    model_config = ConfigDict(from_attributes=True)

    job_id: UUID = Field(description="Unique identifier of the background ingestion job")
    doc_id: UUID = Field(description="Unique identifier of the created document")
    status: str = Field(
        default=JobStatus.PENDING.value,
        description="Initial lifecycle status of the ingestion job",
    )
    message: str = Field(
        default="Ingestion job submitted successfully",
        description="Human-readable confirmation message",
    )


class JobStatusResponse(BaseModel):
    """Response representing the current progress and status of an ingestion job."""

    model_config = ConfigDict(from_attributes=True)

    job_id: UUID = Field(description="Unique identifier of the ingestion job")
    status: str = Field(description="Current lifecycle status of the ingestion job")
    progress_percentage: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Current progress percentage between 0 and 100",
    )
    error_message: str | None = Field(
        default=None,
        description="Error description if the job failed, or None",
    )


class DocumentCheckResponse(BaseModel):
    """Response verifying whether a document URL is actively indexed."""

    model_config = ConfigDict(from_attributes=True)

    exists: bool = Field(description="Whether an active document exists for the URL")
    doc_id: UUID | None = Field(
        default=None,
        description="Document ID if actively present, or None",
    )
    status: str | None = Field(
        default=None,
        description="Latest ingestion job status if actively present, or None",
    )


class DeleteResponse(BaseModel):
    """Response returned upon soft-deleting a document and purging vectors."""

    model_config = ConfigDict(from_attributes=True)

    doc_id: UUID = Field(description="Unique identifier of the soft-deleted document")
    status: str = Field(
        default="deleted",
        description="Operation outcome status",
    )
    message: str = Field(
        default="Document and associated vectors successfully deleted",
        description="Human-readable confirmation message",
    )
