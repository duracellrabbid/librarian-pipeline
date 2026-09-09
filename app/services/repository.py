"""Database repository layer for document and ingestion job operations."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models import Document, IngestionJob, JobStatus


class RepositoryError(Exception):
    """Base exception for database repository operations."""


class DuplicateActiveURLError(RepositoryError):
    """Raised when an active document already exists with the given source URL."""


class JobNotFoundError(RepositoryError):
    """Raised when an ingestion job cannot be found."""


class DocumentNotFoundError(RepositoryError):
    """Raised when a document cannot be found."""


async def check_active_url(session: AsyncSession, url: str) -> Document | None:
    """Retrieve an active (non-deleted) document by its source URL if one exists."""
    statement = select(Document).where(
        Document.source_url == url,
        Document.deleted_at.is_(None),
    )
    result = await session.execute(statement)
    return result.scalars().first()


async def create_document_and_job(
    session: AsyncSession,
    source_type: str,
    source_url: str,
    title: str | None = None,
) -> tuple[Document, IngestionJob]:
    """Register a new document and initialize an associated ingestion job in PENDING status.

    Raises DuplicateActiveURLError if an active document with source_url already exists.
    """
    existing_active = await check_active_url(session, source_url)
    if existing_active is not None:
        raise DuplicateActiveURLError(
            f"Active document already exists for URL: {source_url} (ID: {existing_active.id})"
        )

    document = Document(
        source_type=source_type,
        source_url=source_url,
        title=title,
    )
    session.add(document)
    await session.flush()

    job = IngestionJob(
        document_id=document.id,
        status=JobStatus.PENDING.value,
        progress_percentage=0,
    )
    session.add(job)
    await session.commit()

    await session.refresh(document)
    await session.refresh(job)
    return document, job


async def update_job_status(
    session: AsyncSession,
    job_id: UUID,
    status: JobStatus | str,
    progress_percentage: int | None = None,
    error_message: str | None = None,
) -> IngestionJob:
    """Update ingestion job state, progress percentage, error messages, and finished timestamps.

    Raises JobNotFoundError if no job matching job_id exists.
    """
    statement = select(IngestionJob).where(IngestionJob.id == job_id)
    result = await session.execute(statement)
    job = result.scalars().first()

    if job is None:
        raise JobNotFoundError(f"Job {job_id} not found")

    status_value = status.value if isinstance(status, JobStatus) else str(status)
    job.status = status_value

    if progress_percentage is not None:
        job.progress_percentage = progress_percentage
    elif status_value == JobStatus.INDEXED.value and job.progress_percentage < 100:
        job.progress_percentage = 100

    if error_message is not None:
        job.error_message = error_message

    # Transitioning to terminal states sets finished_at if not already set
    if (
        status_value in (JobStatus.INDEXED.value, JobStatus.FAILED.value)
        and job.finished_at is None
    ):
        job.finished_at = datetime.now(UTC)

    await session.commit()
    await session.refresh(job)
    return job


async def soft_delete_document(session: AsyncSession, doc_id: UUID) -> Document:
    """Soft-delete a document by recording a deleted_at timestamp.

    Raises DocumentNotFoundError if no document matching doc_id exists.
    """
    statement = select(Document).where(Document.id == doc_id)
    result = await session.execute(statement)
    document = result.scalars().first()

    if document is None:
        raise DocumentNotFoundError(f"Document {doc_id} not found")

    now = datetime.now(UTC)
    document.deleted_at = now
    document.updated_at = now

    await session.commit()
    await session.refresh(document)
    return document


async def update_document_metadata(
    session: AsyncSession,
    document_id: UUID,
    *,
    title: str | None = None,
    chunk_count: int | None = None,
    content_hash: str | None = None,
) -> Document:
    """Update document metadata attributes and timestamp.

    Raises DocumentNotFoundError if no document matching document_id exists.
    """
    statement = select(Document).where(Document.id == document_id)
    result = await session.execute(statement)
    document = result.scalars().first()

    if document is None:
        raise DocumentNotFoundError(f"Document {document_id} not found")

    if title is not None:
        document.title = title
    if chunk_count is not None:
        document.chunk_count = chunk_count
    if content_hash is not None:
        document.content_hash = content_hash

    document.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(document)
    return document
