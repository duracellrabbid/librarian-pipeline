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
async def test_update_job_status_auto_progress_100(session: AsyncSession):
    """Verify update_job_status defaults progress_percentage to 100 when status is INDEXED."""
    from app.services.repository import create_document_and_job, update_job_status

    _, job = await create_document_and_job(
        session=session,
        source_type="url",
        source_url="https://example.com/auto-100",
    )
    assert job.progress_percentage == 0

    indexed_job = await update_job_status(
        session=session,
        job_id=job.id,
        status=JobStatus.INDEXED,
    )
    assert indexed_job.status == JobStatus.INDEXED.value
    assert indexed_job.progress_percentage == 100
    assert indexed_job.finished_at is not None


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


@pytest.mark.asyncio
async def test_create_batch_and_jobs_all_accepted(session: AsyncSession):
    """Verify create_batch_and_jobs creates batch and accepted jobs for all new URLs."""
    from app.api.schemas import DocumentIngestItem
    from app.models import BatchJobStatus
    from app.services.repository import create_batch_and_jobs

    items = [
        DocumentIngestItem(url="https://en.wikipedia.org/wiki/Page1", title="Page 1"),
        DocumentIngestItem(url="https://en.wikipedia.org/wiki/Page2", title="Page 2"),
    ]

    batch, accepted, skipped = await create_batch_and_jobs(session, items)

    assert batch.total_count == 2
    assert batch.accepted_count == 2
    assert batch.skipped_count == 0
    assert batch.status == BatchJobStatus.PENDING.value
    assert len(accepted) == 2
    assert len(skipped) == 0

    doc1, job1 = accepted[0]
    assert doc1.source_url == "https://en.wikipedia.org/wiki/Page1"
    assert doc1.title == "Page 1"
    assert job1.batch_id == batch.id
    assert job1.document_id == doc1.id


@pytest.mark.asyncio
async def test_create_batch_and_jobs_with_intra_request_duplicates(session: AsyncSession):
    """Verify create_batch_and_jobs keeps first occurrence and skips subsequent duplicates."""

    from app.api.schemas import DocumentIngestItem
    from app.services.repository import create_batch_and_jobs

    items = [
        DocumentIngestItem(url="https://en.wikipedia.org/wiki/Duplicate", title="First Occurrence"),
        DocumentIngestItem(url="https://en.wikipedia.org/wiki/Duplicate", title="Second Occurrence"),
    ]

    batch, accepted, skipped = await create_batch_and_jobs(session, items)

    assert batch.total_count == 2
    assert batch.accepted_count == 1
    assert batch.skipped_count == 1
    assert len(accepted) == 1
    assert len(skipped) == 1
    assert skipped[0].url == "https://en.wikipedia.org/wiki/Duplicate"
    assert skipped[0].reason == "duplicate_in_request"


@pytest.mark.asyncio
async def test_create_batch_and_jobs_skips_already_indexed(session: AsyncSession):
    """Verify active document with INDEXED status is skipped with already_ingested."""
    from app.api.schemas import DocumentIngestItem
    from app.services.repository import (
        create_batch_and_jobs,
        create_document_and_job,
        update_job_status,
    )

    doc, job = await create_document_and_job(
        session=session,
        source_type="url",
        source_url="https://en.wikipedia.org/wiki/Indexed_Page",
    )
    await update_job_status(session=session, job_id=job.id, status=JobStatus.INDEXED)

    items = [DocumentIngestItem(url="https://en.wikipedia.org/wiki/Indexed_Page")]
    batch, accepted, skipped = await create_batch_and_jobs(session, items)

    assert batch.accepted_count == 0
    assert batch.skipped_count == 1
    assert len(accepted) == 0
    assert len(skipped) == 1
    assert skipped[0].reason == "already_ingested"
    assert skipped[0].existing_doc_id == doc.id


@pytest.mark.asyncio
async def test_create_batch_and_jobs_skips_in_progress(session: AsyncSession):
    """Verify active document in PENDING or processing state is skipped with currently_ingesting."""
    from app.api.schemas import DocumentIngestItem
    from app.services.repository import create_batch_and_jobs, create_document_and_job

    doc, _ = await create_document_and_job(
        session=session,
        source_type="url",
        source_url="https://en.wikipedia.org/wiki/Ingesting_Page",
    )

    items = [DocumentIngestItem(url="https://en.wikipedia.org/wiki/Ingesting_Page")]
    batch, accepted, skipped = await create_batch_and_jobs(session, items)

    assert batch.accepted_count == 0
    assert batch.skipped_count == 1
    assert len(skipped) == 1
    assert skipped[0].reason == "currently_ingesting"
    assert skipped[0].existing_doc_id == doc.id


@pytest.mark.asyncio
async def test_create_batch_and_jobs_reingests_failed(session: AsyncSession):
    """Verify active document whose latest job FAILED is accepted for re-ingestion."""
    from app.api.schemas import DocumentIngestItem
    from app.services.repository import (
        create_batch_and_jobs,
        create_document_and_job,
        update_job_status,
    )

    doc, job = await create_document_and_job(
        session=session,
        source_type="url",
        source_url="https://en.wikipedia.org/wiki/Failed_Page",
    )
    await update_job_status(session=session, job_id=job.id, status=JobStatus.FAILED)

    items = [DocumentIngestItem(url="https://en.wikipedia.org/wiki/Failed_Page")]
    batch, accepted, skipped = await create_batch_and_jobs(session, items)

    assert batch.accepted_count == 1
    assert batch.skipped_count == 0
    assert len(accepted) == 1
    new_doc, new_job = accepted[0]
    assert new_doc.id == doc.id  # reuses existing document
    assert new_job.id != job.id  # creates new job
    assert new_job.batch_id == batch.id


@pytest.mark.asyncio
async def test_get_batch_job_status_success(session: AsyncSession):
    """Verify get_batch_job_status retrieves aggregated counts and child job statuses."""
    from app.api.schemas import DocumentIngestItem
    from app.models import BatchJobStatus
    from app.services.repository import (
        create_batch_and_jobs,
        get_batch_job_status,
        update_job_status,
    )

    items = [
        DocumentIngestItem(url="https://en.wikipedia.org/wiki/P1"),
        DocumentIngestItem(url="https://en.wikipedia.org/wiki/P2"),
    ]
    batch, accepted, _ = await create_batch_and_jobs(session, items)
    job1_id = accepted[0][1].id
    job2_id = accepted[1][1].id

    # Update job1 to INDEXED and job2 to SCRAPING
    await update_job_status(session, job1_id, JobStatus.INDEXED, progress_percentage=100)
    await update_job_status(session, job2_id, JobStatus.SCRAPING, progress_percentage=50)

    status_resp = await get_batch_job_status(session, batch.id)

    assert status_resp.main_job_id == batch.id
    assert status_resp.status == BatchJobStatus.PROCESSING.value
    assert status_resp.total_jobs == 2
    assert status_resp.completed_jobs == 1
    assert status_resp.failed_jobs == 0
    assert status_resp.overall_progress_percentage == 75
    assert len(status_resp.jobs) == 2


@pytest.mark.asyncio
async def test_get_batch_job_status_not_found(session: AsyncSession):
    """Verify get_batch_job_status raises JobNotFoundError when batch_id does not exist."""
    from app.services.repository import JobNotFoundError, get_batch_job_status

    missing_id = uuid4()
    with pytest.raises(JobNotFoundError, match=f"Batch job {missing_id} not found"):
        await get_batch_job_status(session, missing_id)


@pytest.mark.asyncio
async def test_get_batch_job_status_all_skipped_total_jobs_zero(session: AsyncSession):
    """Verify get_batch_job_status when all URLs in the batch were skipped."""
    from app.api.schemas import DocumentIngestItem
    from app.models import BatchJobStatus
    from app.services.repository import create_batch_and_jobs, get_batch_job_status

    items = [
        DocumentIngestItem(url="https://en.wikipedia.org/wiki/DupStatus"),
        DocumentIngestItem(url="https://en.wikipedia.org/wiki/DupStatus"),
    ]
    # First batch accepts one, second batch with same URL will skip all
    await create_batch_and_jobs(session, [DocumentIngestItem(url="https://en.wikipedia.org/wiki/DupStatus")])
    batch2, _, _ = await create_batch_and_jobs(session, items)

    status_resp = await get_batch_job_status(session, batch2.id)
    assert status_resp.total_jobs == 0
    assert status_resp.status == BatchJobStatus.COMPLETED.value
    assert status_resp.overall_progress_percentage == 100


@pytest.mark.asyncio
async def test_get_batch_job_status_all_completed(session: AsyncSession):
    """Verify get_batch_job_status transitions to COMPLETED when all child jobs are INDEXED."""
    from app.api.schemas import DocumentIngestItem
    from app.models import BatchJobStatus
    from app.services.repository import (
        create_batch_and_jobs,
        get_batch_job_status,
        update_job_status,
    )

    items = [DocumentIngestItem(url="https://en.wikipedia.org/wiki/C1")]
    batch, accepted, _ = await create_batch_and_jobs(session, items)
    await update_job_status(session, accepted[0][1].id, JobStatus.INDEXED)

    status_resp = await get_batch_job_status(session, batch.id)
    assert status_resp.status == BatchJobStatus.COMPLETED.value
    assert status_resp.completed_jobs == 1
    assert status_resp.overall_progress_percentage == 100


@pytest.mark.asyncio
async def test_get_batch_job_status_all_failed(session: AsyncSession):
    """Verify get_batch_job_status transitions to FAILED when all child jobs are FAILED."""
    from app.api.schemas import DocumentIngestItem
    from app.models import BatchJobStatus
    from app.services.repository import (
        create_batch_and_jobs,
        get_batch_job_status,
        update_job_status,
    )

    items = [DocumentIngestItem(url="https://en.wikipedia.org/wiki/F1")]
    batch, accepted, _ = await create_batch_and_jobs(session, items)
    await update_job_status(session, accepted[0][1].id, JobStatus.FAILED)

    status_resp = await get_batch_job_status(session, batch.id)
    assert status_resp.status == BatchJobStatus.FAILED.value
    assert status_resp.failed_jobs == 1


@pytest.mark.asyncio
async def test_get_batch_job_status_partially_failed(session: AsyncSession):
    """Verify get_batch_job_status transitions to PARTIALLY_FAILED when jobs partially fail."""

    from app.api.schemas import DocumentIngestItem
    from app.models import BatchJobStatus
    from app.services.repository import (
        create_batch_and_jobs,
        get_batch_job_status,
        update_job_status,
    )

    items = [
        DocumentIngestItem(url="https://en.wikipedia.org/wiki/PF1"),
        DocumentIngestItem(url="https://en.wikipedia.org/wiki/PF2"),
    ]
    batch, accepted, _ = await create_batch_and_jobs(session, items)
    await update_job_status(session, accepted[0][1].id, JobStatus.INDEXED)
    await update_job_status(session, accepted[1][1].id, JobStatus.FAILED)

    status_resp = await get_batch_job_status(session, batch.id)
    assert status_resp.status == BatchJobStatus.PARTIALLY_FAILED.value
    assert status_resp.completed_jobs == 1
    assert status_resp.failed_jobs == 1


@pytest.mark.asyncio
async def test_get_batch_job_status_pending(session: AsyncSession):
    """Verify get_batch_job_status remains PENDING when all child jobs are PENDING."""
    from app.api.schemas import DocumentIngestItem
    from app.models import BatchJobStatus
    from app.services.repository import create_batch_and_jobs, get_batch_job_status

    items = [DocumentIngestItem(url="https://en.wikipedia.org/wiki/Pend1")]
    batch, _, _ = await create_batch_and_jobs(session, items)

    status_resp = await get_batch_job_status(session, batch.id)
    assert status_resp.status == BatchJobStatus.PENDING.value
    assert status_resp.overall_progress_percentage == 0


@pytest.mark.asyncio
async def test_update_document_metadata_success(session: AsyncSession):
    """Verify update_document_metadata updates title, chunk_count, and content_hash."""
    from app.services.repository import create_document_and_job, update_document_metadata

    doc, _ = await create_document_and_job(
        session=session,
        source_type="url",
        source_url="https://example.com/metadata-test",
    )

    updated = await update_document_metadata(
        session=session,
        document_id=doc.id,
        title="Updated Title",
        chunk_count=5,
        content_hash="hash123",
    )

    assert updated.title == "Updated Title"
    assert updated.chunk_count == 5
    assert updated.content_hash == "hash123"


@pytest.mark.asyncio
async def test_update_document_metadata_not_found(session: AsyncSession):
    """Verify update_document_metadata raises DocumentNotFoundError when document does not exist."""
    from app.services.repository import DocumentNotFoundError, update_document_metadata

    missing_id = uuid4()
    with pytest.raises(DocumentNotFoundError, match=f"Document {missing_id} not found"):
        await update_document_metadata(session=session, document_id=missing_id, title="Test")


@pytest.mark.asyncio
async def test_list_indexed_documents_default_pagination(session: AsyncSession):
    """Verify list_indexed_documents default pagination returns max 20 items
    and accurate total count.
    """
    from app.services.repository import (
        create_document_and_job,
        list_indexed_documents,
        update_job_status,
    )

    for i in range(25):
        doc, job = await create_document_and_job(
            session=session,
            source_type="url",
            source_url=f"https://example.com/doc-{i:02d}",
            title=f"Doc {i:02d}",
        )
        await update_job_status(session, job.id, JobStatus.INDEXED)

    total, items = await list_indexed_documents(session)

    assert total == 25
    assert len(items) == 20
    assert items[0].status == JobStatus.INDEXED.value
    assert items[0].source_url.startswith("https://example.com/doc-")


@pytest.mark.asyncio
async def test_list_indexed_documents_custom_limit_offset(session: AsyncSession):
    """Verify list_indexed_documents custom limit and offset slicing."""
    from app.services.repository import (
        create_document_and_job,
        list_indexed_documents,
        update_job_status,
    )

    for i in range(5):
        doc, job = await create_document_and_job(
            session=session,
            source_type="url",
            source_url=f"https://example.com/slice-{i}",
            title=f"Slice {i}",
        )
        await update_job_status(session, job.id, JobStatus.INDEXED)

    total, items = await list_indexed_documents(session, limit=2, offset=1)

    assert total == 5
    assert len(items) == 2


@pytest.mark.asyncio
async def test_list_indexed_documents_substring_filter(session: AsyncSession):
    """Verify list_indexed_documents filters by URL and title substring case-insensitively."""
    from app.services.repository import (
        create_document_and_job,
        list_indexed_documents,
        update_job_status,
    )

    d1, j1 = await create_document_and_job(
        session=session,
        source_type="url",
        source_url="https://example.com/quantum-physics",
        title="Intro to Physics",
    )
    await update_job_status(session, j1.id, JobStatus.INDEXED)

    d2, j2 = await create_document_and_job(
        session=session,
        source_type="url",
        source_url="https://example.com/ai-agents",
        title="Quantum Computing Advances",
    )
    await update_job_status(session, j2.id, JobStatus.INDEXED)

    d3, j3 = await create_document_and_job(
        session=session,
        source_type="url",
        source_url="https://example.com/biology",
        title="Cell Structure",
    )
    await update_job_status(session, j3.id, JobStatus.INDEXED)

    total_q, items_q = await list_indexed_documents(session, query="quantum")
    assert total_q == 2
    assert {item.id for item in items_q} == {d1.id, d2.id}

    total_p, items_p = await list_indexed_documents(session, query="PHYSICS")
    assert total_p == 1
    assert items_p[0].id == d1.id

    total_none, items_none = await list_indexed_documents(session, query="nonexistent")
    assert total_none == 0
    assert len(items_none) == 0


@pytest.mark.asyncio
async def test_list_indexed_documents_excludes_soft_deleted(session: AsyncSession):
    """Verify list_indexed_documents excludes soft-deleted documents."""
    from app.services.repository import (
        create_document_and_job,
        list_indexed_documents,
        soft_delete_document,
        update_job_status,
    )

    d1, j1 = await create_document_and_job(
        session=session,
        source_type="url",
        source_url="https://example.com/active",
        title="Active Doc",
    )
    await update_job_status(session, j1.id, JobStatus.INDEXED)

    d2, j2 = await create_document_and_job(
        session=session,
        source_type="url",
        source_url="https://example.com/deleted",
        title="Deleted Doc",
    )
    await update_job_status(session, j2.id, JobStatus.INDEXED)
    await soft_delete_document(session, d2.id)

    total, items = await list_indexed_documents(session)
    assert total == 1
    assert items[0].id == d1.id


@pytest.mark.asyncio
async def test_list_indexed_documents_excludes_non_indexed_jobs(session: AsyncSession):
    """Verify list_indexed_documents excludes documents whose latest job is not INDEXED."""
    from app.services.repository import (
        create_document_and_job,
        list_indexed_documents,
        update_job_status,
    )

    d1, j1 = await create_document_and_job(
        session=session,
        source_type="url",
        source_url="https://example.com/indexed",
        title="Indexed Doc",
    )
    await update_job_status(session, j1.id, JobStatus.INDEXED)

    d2, j2 = await create_document_and_job(
        session=session,
        source_type="url",
        source_url="https://example.com/pending",
        title="Pending Doc",
    )
    # job remains PENDING

    d3, j3 = await create_document_and_job(
        session=session,
        source_type="url",
        source_url="https://example.com/failed",
        title="Failed Doc",
    )
    await update_job_status(session, j3.id, JobStatus.FAILED)

    total, items = await list_indexed_documents(session)
    assert total == 1
    assert items[0].id == d1.id


@pytest.mark.asyncio
async def test_list_indexed_documents_multiple_jobs_latest_status(session: AsyncSession):
    """Verify list_indexed_documents respects only the latest job status for a document."""
    from datetime import UTC, datetime, timedelta

    from app.services.repository import create_document_and_job, list_indexed_documents

    # Document A: old job FAILED, newer job INDEXED -> should be included
    da, ja1 = await create_document_and_job(
        session=session,
        source_type="url",
        source_url="https://example.com/reingested-success",
        title="Reingested Success",
    )
    ja1.created_at = datetime.now(UTC) - timedelta(hours=2)
    ja1.status = JobStatus.FAILED.value
    session.add(ja1)
    await session.commit()

    ja2 = IngestionJob(
        document_id=da.id,
        status=JobStatus.INDEXED.value,
        progress_percentage=100,
        created_at=datetime.now(UTC) - timedelta(hours=1),
    )
    session.add(ja2)
    await session.commit()

    # Document B: old job INDEXED, newer job FAILED -> should be excluded
    db, jb1 = await create_document_and_job(
        session=session,
        source_type="url",
        source_url="https://example.com/reingested-failed",
        title="Reingested Failed",
    )
    jb1.created_at = datetime.now(UTC) - timedelta(hours=2)
    jb1.status = JobStatus.INDEXED.value
    session.add(jb1)
    await session.commit()

    jb2 = IngestionJob(
        document_id=db.id,
        status=JobStatus.FAILED.value,
        progress_percentage=0,
        created_at=datetime.now(UTC) - timedelta(hours=1),
    )
    session.add(jb2)
    await session.commit()

    total, items = await list_indexed_documents(session)
    assert total == 1
    assert items[0].id == da.id


@pytest.mark.asyncio
async def test_create_batch_and_jobs_skips_unallowed_domain(session: AsyncSession):
    """Verify create_batch_and_jobs skips URLs from unallowed domains with domain_not_allowed."""
    from app.api.schemas import DocumentIngestItem
    from app.models import BatchJobStatus
    from app.services.repository import create_batch_and_jobs

    items = [
        DocumentIngestItem(url="https://unallowed.com/article", title="Unallowed"),
    ]

    batch, accepted, skipped = await create_batch_and_jobs(session, items)

    assert batch.total_count == 1
    assert batch.accepted_count == 0
    assert batch.skipped_count == 1
    assert len(accepted) == 0
    assert len(skipped) == 1
    assert skipped[0].url == "https://unallowed.com/article"
    assert skipped[0].reason == "domain_not_allowed"
    assert batch.status == BatchJobStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_create_batch_and_jobs_mixed_allowed_and_unallowed_domains(session: AsyncSession):
    """Verify create_batch_and_jobs accepts allowed domains while skipping unallowed domains."""
    from app.api.schemas import DocumentIngestItem
    from app.models import BatchJobStatus
    from app.services.repository import create_batch_and_jobs

    items = [
        DocumentIngestItem(url="https://en.wikipedia.org/wiki/Python", title="Wikipedia Python"),
        DocumentIngestItem(url="https://evil.com/malware", title="Evil Malware"),
    ]

    batch, accepted, skipped = await create_batch_and_jobs(session, items)

    assert batch.total_count == 2
    assert batch.accepted_count == 1
    assert batch.skipped_count == 1
    assert batch.status == BatchJobStatus.PENDING.value
    assert len(accepted) == 1
    assert len(skipped) == 1
    assert accepted[0][0].source_url == "https://en.wikipedia.org/wiki/Python"
    assert skipped[0].url == "https://evil.com/malware"
    assert skipped[0].reason == "domain_not_allowed"


@pytest.mark.asyncio
async def test_create_batch_and_jobs_custom_allowed_domains(session: AsyncSession):
    """Verify create_batch_and_jobs respects explicit allowed_domains argument if provided."""
    from app.api.schemas import DocumentIngestItem
    from app.services.repository import create_batch_and_jobs

    items = [
        DocumentIngestItem(url="https://custom.org/doc1", title="Custom 1"),
        DocumentIngestItem(url="https://en.wikipedia.org/wiki/Doc2", title="Wiki 2"),
    ]

    batch, accepted, skipped = await create_batch_and_jobs(
        session,
        items,
        allowed_domains=["https://custom.org"],
    )

    assert batch.total_count == 2
    assert batch.accepted_count == 1
    assert batch.skipped_count == 1
    assert accepted[0][0].source_url == "https://custom.org/doc1"
    assert skipped[0].url == "https://en.wikipedia.org/wiki/Doc2"
    assert skipped[0].reason == "domain_not_allowed"


def test_normalize_docset_name_valid():
    """Verify normalize_docset_name normalizes casing and whitespace for valid names."""
    from app.services.repository import normalize_docset_name

    assert normalize_docset_name("Python-Docs ") == "python-docs"
    assert normalize_docset_name("set_1-v2") == "set_1-v2"
    assert normalize_docset_name("  MY_DOCSET  ") == "my_docset"
    assert normalize_docset_name("a" * 64) == "a" * 64


def test_normalize_docset_name_invalid_format():
    """Verify normalize_docset_name raises InvalidDocsetNameError for invalid patterns."""
    from app.services.repository import InvalidDocsetNameError, normalize_docset_name

    with pytest.raises(InvalidDocsetNameError, match="Invalid docset name"):
        normalize_docset_name("")

    with pytest.raises(InvalidDocsetNameError, match="Invalid docset name"):
        normalize_docset_name("   ")

    with pytest.raises(InvalidDocsetNameError, match="Invalid docset name"):
        normalize_docset_name("docset/test")

    with pytest.raises(InvalidDocsetNameError, match="Invalid docset name"):
        normalize_docset_name("docset.name")

    with pytest.raises(InvalidDocsetNameError, match="Invalid docset name"):
        normalize_docset_name("a" * 65)


def test_normalize_docset_name_reserved_keyword():
    """Verify normalize_docset_name rejects the reserved 'default' keyword."""
    from app.services.repository import ReservedDocsetNameError, normalize_docset_name

    with pytest.raises(ReservedDocsetNameError, match="reserved"):
        normalize_docset_name("default")

    with pytest.raises(ReservedDocsetNameError, match="reserved"):
        normalize_docset_name("DEFAULT")

    with pytest.raises(ReservedDocsetNameError, match="reserved"):
        normalize_docset_name("  default  ")


@pytest.mark.asyncio
async def test_check_active_url_scoped_to_docset(session: AsyncSession):
    """Verify check_active_url isolates active checks by docset."""
    from app.models import Docset, Document
    from app.services.repository import check_active_url

    session.add_all(
        [
            Docset(name="docset-x"),
            Docset(name="docset-y"),
            Document(source_type="url", source_url="https://example.com/unique-page", docset="docset-x"),
        ]
    )
    await session.commit()

    # Found in docset-x
    doc_x = await check_active_url(session, "https://example.com/unique-page", docset="docset-x")
    assert doc_x is not None
    assert doc_x.docset == "docset-x"

    # Absent in docset-y
    doc_y = await check_active_url(session, "https://example.com/unique-page", docset="docset-y")
    assert doc_y is None


@pytest.mark.asyncio
async def test_create_batch_and_jobs_auto_creates_docset(session: AsyncSession):
    """Verify create_batch_and_jobs auto-creates docset if not present."""
    from app.api.schemas import DocumentIngestItem
    from app.models import Docset
    from app.services.repository import create_batch_and_jobs
    from sqlmodel import select

    items = [DocumentIngestItem(url="https://en.wikipedia.org/wiki/Deep_learning", title="DL")]

    batch, accepted, skipped = await create_batch_and_jobs(
        session,
        items,
        docset="ml-docs",
    )

    assert batch.accepted_count == 1
    assert len(accepted) == 1
    doc, job = accepted[0]
    assert doc.docset == "ml-docs"

    query = select(Docset).where(Docset.name == "ml-docs")
    res = await session.execute(query)
    stored_docset = res.scalar_one()
    assert stored_docset.name == "ml-docs"
    assert stored_docset.document_count == 1
    assert stored_docset.deleted_at is None


@pytest.mark.asyncio
async def test_create_batch_and_jobs_revives_pruned_docset(session: AsyncSession):
    """Verify create_batch_and_jobs revives a previously pruned docset."""
    from datetime import UTC, datetime

    from app.api.schemas import DocumentIngestItem
    from app.models import Docset
    from app.services.repository import create_batch_and_jobs
    from sqlmodel import select

    pruned = Docset(name="revived-set", document_count=0, deleted_at=datetime.now(UTC))
    session.add(pruned)
    await session.commit()

    items = [DocumentIngestItem(url="https://en.wikipedia.org/wiki/Revival", title="Revival")]
    batch, accepted, _ = await create_batch_and_jobs(session, items, docset="revived-set")

    assert batch.accepted_count == 1
    query = select(Docset).where(Docset.name == "revived-set")
    res = await session.execute(query)
    stored_docset = res.scalar_one()
    assert stored_docset.deleted_at is None
    assert stored_docset.document_count == 1


@pytest.mark.asyncio
async def test_create_batch_and_jobs_same_url_across_different_docsets(session: AsyncSession):
    """Verify identical URL is accepted into different docsets independently."""
    from app.api.schemas import DocumentIngestItem
    from app.models import JobStatus
    from app.services.repository import create_batch_and_jobs

    items = [DocumentIngestItem(url="https://en.wikipedia.org/wiki/Shared_Topic", title="Shared")]

    # 1. Ingest into docset-alpha and mark as INDEXED
    batch1, accepted1, _ = await create_batch_and_jobs(session, items, docset="docset-alpha")
    assert batch1.accepted_count == 1
    doc1, job1 = accepted1[0]
    job1.status = JobStatus.INDEXED.value
    await session.commit()

    # 2. Ingest same URL into docset-beta -> must be accepted!
    batch2, accepted2, skipped2 = await create_batch_and_jobs(session, items, docset="docset-beta")
    assert batch2.accepted_count == 1
    assert len(skipped2) == 0
    doc2, job2 = accepted2[0]
    assert doc2.id != doc1.id
    assert doc2.docset == "docset-beta"


@pytest.mark.asyncio
async def test_create_batch_and_jobs_reactivates_soft_deleted_document(session: AsyncSession):
    """Verify re-submitting a soft-deleted URL in the same docset re-activates it."""
    from datetime import UTC, datetime

    from app.api.schemas import DocumentIngestItem
    from app.models import JobStatus
    from app.services.repository import create_batch_and_jobs

    items = [DocumentIngestItem(url="https://en.wikipedia.org/wiki/Recycled", title="Initial")]

    # 1. First ingestion
    batch1, accepted1, _ = await create_batch_and_jobs(session, items, docset="recycled-set")
    doc1, job1 = accepted1[0]
    doc1.chunk_count = 5
    doc1.content_hash = "abc123hash"
    job1.status = JobStatus.INDEXED.value
    await session.commit()

    # 2. Soft-delete the document
    doc1.deleted_at = datetime.now(UTC)
    await session.commit()

    # 3. Re-ingest same URL into the same docset
    items2 = [DocumentIngestItem(url="https://en.wikipedia.org/wiki/Recycled", title="Re-activated")]
    batch2, accepted2, skipped2 = await create_batch_and_jobs(session, items2, docset="recycled-set")

    assert batch2.accepted_count == 1
    assert len(skipped2) == 0
    doc2, job2 = accepted2[0]
    assert doc2.id == doc1.id
    assert doc2.deleted_at is None
    assert doc2.title == "Re-activated"
    assert doc2.chunk_count == 0
    assert doc2.content_hash is None


@pytest.mark.asyncio
async def test_check_active_url_and_check_document_by_url(session: AsyncSession):
    """Verify check_active_url and check_document_by_url filter by docset and deleted_at."""
    from datetime import UTC, datetime

    from app.models import Document
    from app.services.repository import check_active_url, check_document_by_url

    doc_active = Document(
        source_type="url",
        source_url="https://example.com/check-test",
        docset="test-docset",
        title="Active Doc",
    )
    doc_deleted = Document(
        source_type="url",
        source_url="https://example.com/check-deleted",
        docset="test-docset",
        title="Deleted Doc",
        deleted_at=datetime.now(UTC),
    )
    session.add(doc_active)
    session.add(doc_deleted)
    await session.commit()

    # Active doc checks
    assert await check_active_url(session, "https://example.com/check-test", docset="test-docset") is not None
    assert await check_active_url(session, "https://example.com/check-test", docset="other-docset") is None
    assert (
        await check_document_by_url(
            session, "https://example.com/check-test", docset="test-docset", include_deleted=False
        )
        is not None
    )
    assert (
        await check_document_by_url(
            session, "https://example.com/check-test", docset="test-docset", include_deleted=True
        )
        is not None
    )

    # Deleted doc checks
    assert await check_active_url(session, "https://example.com/check-deleted", docset="test-docset") is None
    assert (
        await check_document_by_url(
            session, "https://example.com/check-deleted", docset="test-docset", include_deleted=False
        )
        is None
    )
    assert (
        await check_document_by_url(
            session, "https://example.com/check-deleted", docset="test-docset", include_deleted=True
        )
        is not None
    )


@pytest.mark.asyncio
async def test_list_active_docsets_filtering_and_pagination(session: AsyncSession):
    """Verify list_active_docsets includes only active docsets with documents and respects pagination."""
    from datetime import UTC, datetime

    from app.models import Docset
    from app.services.repository import list_active_docsets

    now = datetime.now(UTC)
    docset1 = Docset(name="active-alpha", document_count=3, created_at=now, updated_at=now)
    docset2 = Docset(name="active-beta", document_count=1, created_at=now, updated_at=now)
    docset_empty = Docset(name="empty-set", document_count=0, created_at=now, updated_at=now)
    docset_pruned = Docset(name="pruned-set", document_count=2, deleted_at=now, created_at=now, updated_at=now)

    session.add(docset1)
    session.add(docset2)
    session.add(docset_empty)
    session.add(docset_pruned)
    await session.commit()

    total, items = await list_active_docsets(session, limit=10, offset=0)
    assert total == 2
    names = [d.name for d in items]
    assert names == ["active-alpha", "active-beta"]

    # Test pagination
    total_paged, items_paged = await list_active_docsets(session, limit=1, offset=1)
    assert total_paged == 2
    assert len(items_paged) == 1
    assert items_paged[0].name == "active-beta"


@pytest.mark.asyncio
async def test_delete_docset_soft_deletes_documents_and_prunes(session: AsyncSession):
    """Verify delete_docset soft-deletes all member documents and marks the docset pruned."""
    from app.api.schemas import DocumentIngestItem
    from app.models import Docset, Document
    from app.services.repository import create_batch_and_jobs, delete_docset
    from sqlmodel import select

    items = [
        DocumentIngestItem(url="https://en.wikipedia.org/wiki/Doc1"),
        DocumentIngestItem(url="https://en.wikipedia.org/wiki/Doc2"),
    ]
    await create_batch_and_jobs(session, items, docset="bulk-del-set")

    deleted_count = await delete_docset(session, "bulk-del-set")
    assert deleted_count == 2

    # Verify docset is pruned
    res = await session.execute(select(Docset).where(Docset.name == "bulk-del-set"))
    ds = res.scalar_one()
    assert ds.deleted_at is not None
    assert ds.document_count == 0

    # Verify documents are soft-deleted
    doc_res = await session.execute(select(Document).where(Document.docset == "bulk-del-set"))
    docs = doc_res.scalars().all()
    assert len(docs) == 2
    assert all(d.deleted_at is not None for d in docs)


@pytest.mark.asyncio
async def test_delete_docset_not_found_raises_error(session: AsyncSession):
    """Verify delete_docset raises DocsetNotFoundError when docset does not exist or has no active docs."""
    from app.services.repository import DocsetNotFoundError, delete_docset

    with pytest.raises(DocsetNotFoundError):
        await delete_docset(session, "nonexistent-docset")


@pytest.mark.asyncio
async def test_soft_delete_document_scoped_and_auto_prunes(session: AsyncSession):
    """Verify soft_delete_document updates docset count and auto-prunes docset on zero active docs."""
    from app.api.schemas import DocumentIngestItem
    from app.models import Docset
    from app.services.repository import (
        DocumentNotFoundError,
        create_batch_and_jobs,
        soft_delete_document,
    )
    from sqlmodel import select

    items = [
        DocumentIngestItem(url="https://en.wikipedia.org/wiki/ItemA"),
        DocumentIngestItem(url="https://en.wikipedia.org/wiki/ItemB"),
    ]
    _, accepted, _ = await create_batch_and_jobs(session, items, docset="auto-prune-set")
    doc_a, _ = accepted[0]
    doc_b, _ = accepted[1]

    # Mismatched docset raises DocumentNotFoundError
    with pytest.raises(DocumentNotFoundError):
        await soft_delete_document(session, doc_a.id, docset="wrong-docset")

    # Delete first doc -> count becomes 1, docset still active
    await soft_delete_document(session, doc_a.id, docset="auto-prune-set")
    res = await session.execute(select(Docset).where(Docset.name == "auto-prune-set"))
    ds = res.scalar_one()
    assert ds.document_count == 1
    assert ds.deleted_at is None

    # Delete second doc -> count becomes 0, docset auto-pruned
    await soft_delete_document(session, doc_b.id, docset="auto-prune-set")
    res2 = await session.execute(select(Docset).where(Docset.name == "auto-prune-set"))
    ds2 = res2.scalar_one()
    assert ds2.document_count == 0
    assert ds2.deleted_at is not None


@pytest.mark.asyncio
async def test_list_indexed_documents_scoped_to_docset(session: AsyncSession):
    """Verify list_indexed_documents filters by docset when provided."""
    from app.api.schemas import DocumentIngestItem
    from app.models import JobStatus
    from app.services.repository import (
        create_batch_and_jobs,
        list_indexed_documents,
        update_job_status,
    )

    items_a = [DocumentIngestItem(url="https://en.wikipedia.org/wiki/SetA_Doc")]
    items_b = [DocumentIngestItem(url="https://en.wikipedia.org/wiki/SetB_Doc")]

    _, accepted_a, _ = await create_batch_and_jobs(session, items_a, docset="set-a")
    _, accepted_b, _ = await create_batch_and_jobs(session, items_b, docset="set-b")

    _, job_a = accepted_a[0]
    _, job_b = accepted_b[0]
    await update_job_status(session, job_a.id, JobStatus.INDEXED)
    await update_job_status(session, job_b.id, JobStatus.INDEXED)

    # Scoped to set-a
    total_a, list_a = await list_indexed_documents(session, docset="set-a")
    assert total_a == 1
    assert list_a[0].source_url == "https://en.wikipedia.org/wiki/SetA_Doc"

    # Scoped to set-b
    total_b, list_b = await list_indexed_documents(session, docset="set-b")
    assert total_b == 1
    assert list_b[0].source_url == "https://en.wikipedia.org/wiki/SetB_Doc"

    # Unscoped lists both
    total_all, list_all = await list_indexed_documents(session)
    assert total_all == 2
