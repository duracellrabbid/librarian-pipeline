"""Request and response Pydantic schemas for the REST API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.models.job import BatchJobStatus, JobStatus


class DocumentIngestItem(BaseModel):
    """Specification of an individual document source within a batch ingestion request."""

    model_config = ConfigDict(from_attributes=True)

    url: HttpUrl = Field(description="Target web URL to scrape and index")
    title: str | None = Field(default=None, description="Optional document title or label")
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional metadata associated with the document",
    )


class IngestRequest(BaseModel):
    """Payload for submitting a batch document ingestion request."""

    model_config = ConfigDict(from_attributes=True)

    documents: list[DocumentIngestItem] = Field(
        min_length=1,
        description="List of document targets to scrape and index",
    )


class IngestResponse(BaseModel):
    """Response returned upon successful batch document ingestion submission."""

    model_config = ConfigDict(from_attributes=True)

    main_job_id: UUID = Field(description="Unique identifier of the batch ingestion job")
    status: str = Field(
        default=BatchJobStatus.PENDING.value,
        description="Initial lifecycle status of the batch ingestion job",
    )
    total_submitted: int = Field(
        default=0,
        ge=0,
        description="Total number of documents submitted in the batch",
    )
    accepted_count: int = Field(
        default=0,
        ge=0,
        description="Number of valid documents accepted for background ingestion",
    )
    skipped_count: int = Field(
        default=0,
        ge=0,
        description="Number of documents skipped due to duplicates or active state",
    )
    message: str = Field(
        default="Ingestion batch submitted successfully",
        description="Human-readable confirmation message",
    )


class ChildJobStatusResponse(BaseModel):
    """Progress and execution status for an individual document within a batch job."""

    model_config = ConfigDict(from_attributes=True)

    url: str = Field(description="Source URL of the document")
    doc_id: UUID | None = Field(
        default=None,
        description="Unique identifier of the created document",
    )
    job_id: UUID | None = Field(
        default=None,
        description="Unique identifier of the child ingestion job",
    )
    status: str = Field(description="Current lifecycle status of the document ingestion")
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


class SkippedDocumentItem(BaseModel):
    """Details of a document URL skipped during batch submission."""

    model_config = ConfigDict(from_attributes=True)

    url: str = Field(description="Source URL of the skipped document")
    reason: str = Field(
        description=("Reason for skipping, e.g. duplicate_in_request, already_ingested, currently_ingesting"),
    )

    existing_doc_id: UUID | None = Field(
        default=None,
        description="Document ID of the existing record if already present",
    )


class JobStatusResponse(BaseModel):
    """Response representing the aggregate progress and per-document breakdown of a batch job."""

    model_config = ConfigDict(from_attributes=True)

    main_job_id: UUID = Field(description="Unique identifier of the batch ingestion job")
    status: str = Field(description="Aggregate lifecycle status of the batch ingestion job")
    overall_progress_percentage: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Overall aggregate progress percentage between 0 and 100",
    )
    total_jobs: int = Field(
        default=0,
        ge=0,
        description="Total number of accepted child jobs tracked under this batch",
    )
    completed_jobs: int = Field(
        default=0,
        ge=0,
        description="Number of completed (INDEXED) child jobs",
    )
    failed_jobs: int = Field(
        default=0,
        ge=0,
        description="Number of failed child jobs",
    )
    jobs: list[ChildJobStatusResponse] = Field(
        default_factory=list,
        description="Status breakdown of accepted child jobs",
    )
    skipped: list[SkippedDocumentItem] = Field(
        default_factory=list,
        description="List of documents skipped during submission and reasons",
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


class DocumentListItemResponse(BaseModel):
    """Specification of an individual indexed document within a paginated list."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="Unique identifier of the document")
    source_url: str = Field(description="Source URL of the indexed document")
    title: str | None = Field(default=None, description="Extracted or provided title")
    status: str = Field(
        default=JobStatus.INDEXED.value,
        description="Current lifecycle status of the document",
    )
    chunk_count: int = Field(
        default=0,
        ge=0,
        description="Total number of chunks indexed for document",
    )
    created_at: datetime = Field(description="Timestamp when the document was created")
    updated_at: datetime = Field(description="Timestamp when the document was last updated")


class DocumentListResponse(BaseModel):
    """Paginated list of actively indexed documents."""

    model_config = ConfigDict(from_attributes=True)

    total: int = Field(default=0, ge=0, description="Total number of matching indexed documents")
    limit: int = Field(default=20, ge=1, le=100, description="Page limit applied to query")
    offset: int = Field(default=0, ge=0, description="Offset applied to query")
    items: list[DocumentListItemResponse] = Field(
        default_factory=list,
        description="List of indexed document records",
    )
