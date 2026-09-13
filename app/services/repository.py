"""Database repository layer for document and ingestion job operations."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.schemas import (
    ChildJobStatusResponse,
    DocumentIngestItem,
    DocumentListItemResponse,
    JobStatusResponse,
    SkippedDocumentItem,
)
from app.models import (
    BatchIngestionJob,
    BatchJobStatus,
    Document,
    IngestionJob,
    JobStatus,
)


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


def _deduplicate_items(
    items: Sequence[DocumentIngestItem],
) -> tuple[list[DocumentIngestItem], list[SkippedDocumentItem]]:
    """Partition items into unique items and duplicates within the request payload."""
    seen: set[str] = set()
    unique_items: list[DocumentIngestItem] = []
    skipped: list[SkippedDocumentItem] = []

    for item in items:
        url_str = str(item.url)
        if url_str in seen:
            skipped.append(SkippedDocumentItem(url=url_str, reason="duplicate_in_request"))
        else:
            seen.add(url_str)
            unique_items.append(item)

    return unique_items, skipped


async def _inspect_single_url_status(
    session: AsyncSession,
    url: str,
) -> tuple[str, Document | None]:
    """Inspect active document for URL and return outcome or skip reason."""

    doc = await check_active_url(session, url)
    if doc is None:
        return "accept_new", None

    statement = select(IngestionJob).where(IngestionJob.document_id == doc.id).order_by(IngestionJob.created_at.desc())
    result = await session.execute(statement)
    latest_job = result.scalars().first()

    if latest_job is None or latest_job.status == JobStatus.FAILED.value:
        return "reingest_failed", doc
    if latest_job.status == JobStatus.INDEXED.value:
        return "already_ingested", doc
    return "currently_ingesting", doc


async def create_batch_and_jobs(
    session: AsyncSession,
    items: Sequence[DocumentIngestItem],
    source_type: str = "url",
) -> tuple[BatchIngestionJob, list[tuple[Document, IngestionJob]], list[SkippedDocumentItem]]:
    """Register a batch and associated documents and jobs with pre-flight status filtering."""
    unique_items, skipped_items = _deduplicate_items(items)

    batch = BatchIngestionJob(
        status=BatchJobStatus.PENDING.value,
        total_count=len(items),
        skipped_details=[],
    )
    session.add(batch)
    await session.flush()

    accepted_pairs: list[tuple[Document, IngestionJob]] = []

    for item in unique_items:
        url_str = str(item.url)
        outcome, existing_doc = await _inspect_single_url_status(session, url_str)

        if outcome in ("already_ingested", "currently_ingesting"):
            skipped_items.append(
                SkippedDocumentItem(
                    url=url_str,
                    reason=outcome,
                    existing_doc_id=existing_doc.id if existing_doc else None,
                )
            )
            continue

        doc = existing_doc or Document(
            source_type=source_type,
            source_url=url_str,
            title=item.title,
        )
        if existing_doc is None:
            session.add(doc)
            await session.flush()

        job = IngestionJob(
            batch_id=batch.id,
            document_id=doc.id,
            status=JobStatus.PENDING.value,
            progress_percentage=0,
        )
        session.add(job)
        accepted_pairs.append((doc, job))

    batch.accepted_count = len(accepted_pairs)
    batch.skipped_count = len(skipped_items)
    batch.skipped_details = [
        {
            "url": s.url,
            "reason": s.reason,
            "existing_doc_id": str(s.existing_doc_id) if s.existing_doc_id else None,
        }
        for s in skipped_items
    ]

    if batch.accepted_count == 0:
        batch.status = BatchJobStatus.COMPLETED.value
        batch.finished_at = datetime.now(UTC)

    await session.commit()
    await session.refresh(batch)
    for doc, job in accepted_pairs:
        await session.refresh(doc)
        await session.refresh(job)

    return batch, accepted_pairs, skipped_items


def _calculate_batch_aggregate(
    child_jobs: Sequence[IngestionJob],
) -> tuple[str, int, int, int, int]:
    """Compute (status, overall_progress, total_jobs, completed_jobs, failed_jobs)."""
    total_jobs = len(child_jobs)
    if total_jobs == 0:
        return BatchJobStatus.COMPLETED.value, 100, 0, 0, 0

    completed = sum(1 for j in child_jobs if j.status == JobStatus.INDEXED.value)
    failed = sum(1 for j in child_jobs if j.status == JobStatus.FAILED.value)
    in_progress = sum(
        1
        for j in child_jobs
        if j.status
        in (
            JobStatus.SCRAPING.value,
            JobStatus.CHUNKING.value,
            JobStatus.EMBEDDING.value,
        )
    )

    overall_progress = int(sum(j.progress_percentage for j in child_jobs) / total_jobs)

    if completed == total_jobs:
        status = BatchJobStatus.COMPLETED.value
    elif failed == total_jobs:
        status = BatchJobStatus.FAILED.value
    elif (completed + failed == total_jobs) and failed > 0:
        status = BatchJobStatus.PARTIALLY_FAILED.value
    elif in_progress > 0 or completed > 0 or failed > 0:
        status = BatchJobStatus.PROCESSING.value
    else:
        status = BatchJobStatus.PENDING.value

    return status, overall_progress, total_jobs, completed, failed


async def get_batch_job_status(
    session: AsyncSession,
    batch_id: UUID,
) -> JobStatusResponse:
    """Retrieve batch job status, computing aggregate progress and child job breakdown."""
    statement = select(BatchIngestionJob).where(BatchIngestionJob.id == batch_id)
    result = await session.execute(statement)
    batch = result.scalars().first()

    if batch is None:
        raise JobNotFoundError(f"Batch job {batch_id} not found")

    jobs_statement = (
        select(IngestionJob, Document.source_url)
        .join(Document, IngestionJob.document_id == Document.id)
        .where(IngestionJob.batch_id == batch_id)
    )
    jobs_result = await session.execute(jobs_statement)
    rows = jobs_result.all()

    child_jobs = [row[0] for row in rows]
    status_val, overall_progress, total, completed, failed = _calculate_batch_aggregate(child_jobs)

    if batch.status != status_val:
        batch.status = status_val
        if status_val in (
            BatchJobStatus.COMPLETED.value,
            BatchJobStatus.FAILED.value,
            BatchJobStatus.PARTIALLY_FAILED.value,
        ):
            batch.finished_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(batch)

    child_responses = [
        ChildJobStatusResponse(
            url=row[1],
            doc_id=row[0].document_id,
            job_id=row[0].id,
            status=row[0].status,
            progress_percentage=row[0].progress_percentage,
            error_message=row[0].error_message,
        )
        for row in rows
    ]

    skipped_items = [
        SkippedDocumentItem(
            url=item["url"],
            reason=item["reason"],
            existing_doc_id=UUID(item["existing_doc_id"]) if item.get("existing_doc_id") else None,
        )
        for item in (batch.skipped_details or [])
    ]

    return JobStatusResponse(
        main_job_id=batch.id,
        status=batch.status,
        overall_progress_percentage=overall_progress,
        total_jobs=total,
        completed_jobs=completed,
        failed_jobs=failed,
        jobs=child_responses,
        skipped=skipped_items,
    )


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
    if status_value in (JobStatus.INDEXED.value, JobStatus.FAILED.value) and job.finished_at is None:
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


def _build_indexed_documents_filters(query: str | None = None) -> list[Any]:
    """Construct base filter conditions and indexed document subquery."""
    latest_job_time = (
        select(
            IngestionJob.document_id,
            func.max(IngestionJob.created_at).label("max_created_at"),
        )
        .group_by(IngestionJob.document_id)
        .subquery()
    )

    indexed_docs_subquery = (
        select(IngestionJob.document_id)
        .join(
            latest_job_time,
            and_(
                IngestionJob.document_id == latest_job_time.c.document_id,
                IngestionJob.created_at == latest_job_time.c.max_created_at,
            ),
        )
        .where(IngestionJob.status == JobStatus.INDEXED.value)
        .subquery()
    )

    filters: list[Any] = [
        Document.deleted_at.is_(None),
        Document.id.in_(select(indexed_docs_subquery)),
    ]

    if query and query.strip():
        search_pattern = f"%{query.strip()}%"
        filters.append(
            or_(
                Document.source_url.ilike(search_pattern),
                Document.title.ilike(search_pattern),
            )
        )

    return filters


async def list_indexed_documents(
    session: AsyncSession,
    limit: int = 20,
    offset: int = 0,
    query: str | None = None,
) -> tuple[int, list[DocumentListItemResponse]]:
    """Retrieve paginated active documents whose latest ingestion job is INDEXED."""
    filters = _build_indexed_documents_filters(query)

    count_stmt = select(func.count(Document.id)).where(*filters)
    count_result = await session.execute(count_stmt)
    total = count_result.scalar() or 0

    data_stmt = select(Document).where(*filters).order_by(Document.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(data_stmt)
    documents = result.scalars().all()

    items = [
        DocumentListItemResponse(
            id=doc.id,
            source_url=doc.source_url,
            title=doc.title,
            status=JobStatus.INDEXED.value,
            chunk_count=doc.chunk_count,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )
        for doc in documents
    ]

    return total, items
