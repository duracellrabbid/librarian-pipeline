"""Tests for database repository functions and job state machine transitions."""

from uuid import uuid4

import pytest
from app.models import Document, IngestionJob, JobStatus
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel


@pytest.fixture
async def session():
    """Create an isolated in-memory async SQLite database session for repository testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as async_sess:
        yield async_sess

    await engine.dispose()


@pytest.mark.asyncio
async def test_check_active_url_returns_none_when_absent(session: AsyncSession):
    """Verify check_active_url returns None when URL is not registered."""
    from app.services.repository import check_active_url

    found = await check_active_url(session, "https://example.com/not-found")
    assert found is None


@pytest.mark.asyncio
async def test_check_active_url_finds_active_document(session: AsyncSession):
    """Verify check_active_url locates an active document by URL."""
    from app.services.repository import check_active_url, create_document_and_job

    doc, _ = await create_document_and_job(
        session=session,
        source_type="url",
        source_url="https://example.com/page",
        title="Test Page",
    )

    found = await check_active_url(session, "https://example.com/page")
    assert found is not None
    assert found.id == doc.id
    assert found.deleted_at is None


@pytest.mark.asyncio
async def test_create_document_and_job_creates_records(session: AsyncSession):
    """Verify create_document_and_job creates both Document and initial IngestionJob."""
    from app.services.repository import create_document_and_job

    doc, job = await create_document_and_job(
        session=session,
        source_type="url",
        source_url="https://example.com/blog",
        title="Sample Blog",
    )

    assert isinstance(doc, Document)
    assert isinstance(job, IngestionJob)
    assert doc.source_url == "https://example.com/blog"
    assert doc.title == "Sample Blog"
    assert job.document_id == doc.id
    assert job.status == JobStatus.PENDING.value
    assert job.progress_percentage == 0
    assert job.finished_at is None


@pytest.mark.asyncio
async def test_create_document_duplicate_active_url_raises_error(session: AsyncSession):
    """Verify attempting to create duplicate active URL raises DuplicateActiveURLError."""
    from app.services.repository import DuplicateActiveURLError, create_document_and_job

    await create_document_and_job(
        session=session,
        source_type="url",
        source_url="https://example.com/duplicate",
    )

    with pytest.raises(DuplicateActiveURLError, match="Active document already exists"):
        await create_document_and_job(
            session=session,
            source_type="url",
            source_url="https://example.com/duplicate",
        )


@pytest.mark.asyncio
async def test_update_job_status_in_progress(session: AsyncSession):
    """Verify update_job_status updates status and progress during ingestion stages."""
    from app.services.repository import create_document_and_job, update_job_status

    _, job = await create_document_and_job(
        session=session,
        source_type="url",
        source_url="https://example.com/pipeline",
    )

    # Transition to SCRAPING
    updated_job = await update_job_status(
        session=session,
        job_id=job.id,
        status=JobStatus.SCRAPING,
        progress_percentage=25,
    )
    assert updated_job.status == JobStatus.SCRAPING.value
    assert updated_job.progress_percentage == 25
    assert updated_job.finished_at is None

    # Transition to CHUNKING
    updated_job = await update_job_status(
        session=session,
        job_id=job.id,
        status=JobStatus.CHUNKING,
        progress_percentage=50,
    )
    assert updated_job.status == JobStatus.CHUNKING.value
    assert updated_job.progress_percentage == 50

    # Transition to EMBEDDING
    updated_job = await update_job_status(
        session=session,
        job_id=job.id,
        status=JobStatus.EMBEDDING,
        progress_percentage=75,
    )
    assert updated_job.status == JobStatus.EMBEDDING.value
    assert updated_job.progress_percentage == 75


@pytest.mark.asyncio
async def test_update_job_status_terminal_indexed(session: AsyncSession):
    """Verify update_job_status transitions to INDEXED with 100% and sets finished_at."""
    from app.services.repository import create_document_and_job, update_job_status

    _, job = await create_document_and_job(
        session=session,
        source_type="url",
        source_url="https://example.com/complete",
    )

    finished_job = await update_job_status(
        session=session,
        job_id=job.id,
        status=JobStatus.INDEXED,
        progress_percentage=100,
    )

    assert finished_job.status == JobStatus.INDEXED.value
    assert finished_job.progress_percentage == 100
    assert finished_job.finished_at is not None
    assert finished_job.error_message is None


@pytest.mark.asyncio
async def test_update_job_status_terminal_failed(session: AsyncSession):
    """Verify update_job_status records failure error message and sets finished_at."""
    from app.services.repository import create_document_and_job, update_job_status

    _, job = await create_document_and_job(
        session=session,
        source_type="url",
        source_url="https://example.com/fail",
    )

    failed_job = await update_job_status(
        session=session,
        job_id=job.id,
        status=JobStatus.FAILED,
        error_message="Connection timed out while fetching content",
    )

    assert failed_job.status == JobStatus.FAILED.value
    assert failed_job.error_message == "Connection timed out while fetching content"
    assert failed_job.finished_at is not None


@pytest.mark.asyncio
async def test_update_job_status_not_found(session: AsyncSession):
    """Verify update_job_status raises JobNotFoundError when job does not exist."""
    from app.services.repository import JobNotFoundError, update_job_status

    missing_id = uuid4()
    with pytest.raises(JobNotFoundError, match=f"Job {missing_id} not found"):
        await update_job_status(
            session=session,
            job_id=missing_id,
            status=JobStatus.SCRAPING,
        )


@pytest.mark.asyncio
async def test_soft_delete_document_sets_deleted_at(session: AsyncSession):
    """Verify soft_delete_document sets deleted_at timestamp."""
    from app.services.repository import (
        check_active_url,
        create_document_and_job,
        soft_delete_document,
    )

    doc, _ = await create_document_and_job(
        session=session,
        source_type="url",
        source_url="https://example.com/soft-delete",
    )

    deleted_doc = await soft_delete_document(session=session, doc_id=doc.id)
    assert deleted_doc.id == doc.id
    assert deleted_doc.deleted_at is not None

    # check_active_url should now return None
    active_lookup = await check_active_url(session, "https://example.com/soft-delete")
    assert active_lookup is None


@pytest.mark.asyncio
async def test_soft_delete_document_not_found(session: AsyncSession):
    """Verify soft_delete_document raises DocumentNotFoundError when doc id is invalid."""
    from app.services.repository import DocumentNotFoundError, soft_delete_document

    missing_id = uuid4()
    with pytest.raises(DocumentNotFoundError, match=f"Document {missing_id} not found"):
        await soft_delete_document(session=session, doc_id=missing_id)


@pytest.mark.asyncio
async def test_reingest_url_after_soft_delete_succeeds(session: AsyncSession):
    """Verify a URL can be re-ingested after its previous document was soft deleted."""
    from app.services.repository import (
        create_document_and_job,
        soft_delete_document,
    )

    first_doc, first_job = await create_document_and_job(
        session=session,
        source_type="url",
        source_url="https://example.com/reingest",
        title="First Version",
    )

    # Soft delete first document
    await soft_delete_document(session=session, doc_id=first_doc.id)

    # Re-ingest the exact same URL
    second_doc, second_job = await create_document_and_job(
        session=session,
        source_type="url",
        source_url="https://example.com/reingest",
        title="Second Version",
    )

    assert second_doc.id != first_doc.id
    assert second_doc.source_url == "https://example.com/reingest"
    assert second_doc.title == "Second Version"
    assert second_doc.deleted_at is None
    assert second_job.id != first_job.id
    assert second_job.document_id == second_doc.id
