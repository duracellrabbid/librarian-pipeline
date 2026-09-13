"""Unit and persistence tests for SQLModel entities: Document and IngestionJob."""

from datetime import datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import Index
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select


def test_job_status_enum_values():
    """Verify JobStatus enum defines all expected lifecycle states."""
    from app.models.job import JobStatus

    assert JobStatus.PENDING.value == "PENDING"
    assert JobStatus.SCRAPING.value == "SCRAPING"
    assert JobStatus.CHUNKING.value == "CHUNKING"
    assert JobStatus.EMBEDDING.value == "EMBEDDING"
    assert JobStatus.INDEXED.value == "INDEXED"
    assert JobStatus.FAILED.value == "FAILED"


def test_ingestion_job_instantiation_defaults():
    """Verify IngestionJob initializes with generated UUID, status, progress, and created_at."""
    from app.models import IngestionJob, JobStatus

    doc_id = uuid4()
    job = IngestionJob(document_id=doc_id)

    assert isinstance(job.id, UUID)
    assert job.document_id == doc_id
    assert job.status == JobStatus.PENDING.value
    assert job.error_message is None
    assert job.progress_percentage == 0
    assert isinstance(job.created_at, datetime)
    assert job.finished_at is None


def test_ingestion_job_explicit_fields():
    """Verify IngestionJob can be created with explicit values and terminal timestamps."""
    from app.models import IngestionJob, JobStatus

    fixed_id = uuid4()
    doc_id = uuid4()
    finished_time = datetime.now()

    job = IngestionJob(
        id=fixed_id,
        document_id=doc_id,
        status=JobStatus.INDEXED.value,
        progress_percentage=100,
        finished_at=finished_time,
    )

    assert job.id == fixed_id
    assert job.document_id == doc_id
    assert job.status == "INDEXED"
    assert job.progress_percentage == 100
    assert job.finished_at == finished_time


def test_ingestion_job_validation_errors():
    """Verify IngestionJob validates required fields and progress range via model_validate."""
    from app.models import IngestionJob

    # Missing document_id
    with pytest.raises(ValidationError):
        IngestionJob.model_validate({})

    # Invalid progress percentage > 100
    with pytest.raises(ValidationError):
        IngestionJob.model_validate({"document_id": uuid4(), "progress_percentage": 150})

    # Invalid progress percentage < 0
    with pytest.raises(ValidationError):
        IngestionJob.model_validate({"document_id": uuid4(), "progress_percentage": -10})


def test_document_model_instantiation_defaults():
    """Verify Document initializes with generated UUID, timestamps, and default chunk_count."""
    from app.models import Document

    doc = Document(
        source_type="url",
        source_url="https://example.com/docs",
    )

    assert isinstance(doc.id, UUID)
    assert doc.source_type == "url"
    assert doc.source_url == "https://example.com/docs"
    assert doc.title is None
    assert doc.content_hash is None
    assert doc.chunk_count == 0
    assert isinstance(doc.created_at, datetime)
    assert isinstance(doc.updated_at, datetime)
    assert doc.deleted_at is None


def test_document_model_explicit_fields():
    """Verify Document can be created with explicit optional values."""
    from app.models import Document

    fixed_id = uuid4()
    doc = Document(
        id=fixed_id,
        source_type="pdf",
        source_url="https://example.com/file.pdf",
        title="Sample Document",
        content_hash="abc123hash",
        chunk_count=12,
    )

    assert doc.id == fixed_id
    assert doc.source_type == "pdf"
    assert doc.source_url == "https://example.com/file.pdf"
    assert doc.title == "Sample Document"
    assert doc.content_hash == "abc123hash"
    assert doc.chunk_count == 12


def test_document_validation_errors():
    """Verify missing required fields raise validation error via model_validate."""
    from app.models import Document

    with pytest.raises(ValidationError):
        Document.model_validate({})


def test_document_table_name_and_partial_index():
    """Verify Document defines table name and partial unique index on active source_url."""
    from app.models import Document

    assert Document.__tablename__ == "documents"

    # Check table args contains partial index
    indices = [arg for arg in Document.__table_args__ if isinstance(arg, Index)]
    partial_index = next((idx for idx in indices if idx.name == "uq_documents_active_source_url"), None)
    assert partial_index is not None
    assert partial_index.unique is True
    col_names = [col.name if hasattr(col, "name") else str(col) for col in partial_index.columns]
    assert "source_url" in col_names
    where_clause = str(partial_index.dialect_options.get("postgresql", {}).get("where", ""))
    assert "deleted_at IS NULL" in where_clause


def test_document_and_job_relationship():
    """Verify bidirectional relationship between Document and IngestionJob in memory."""
    from app.models import Document, IngestionJob

    doc = Document(source_type="url", source_url="https://example.com")
    job = IngestionJob(document_id=doc.id, document=doc)

    assert job.document is doc


@pytest.mark.asyncio
async def test_database_persistence_and_relationships():
    """Verify Document and IngestionJob persistence and queries against an async engine."""
    from app.models import Document, IngestionJob, JobStatus

    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    test_session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with test_session_factory() as session:
        doc = Document(source_type="url", source_url="https://example.com/article", title="Article")
        session.add(doc)
        await session.flush()

        job = IngestionJob(document_id=doc.id, status=JobStatus.PENDING.value)
        session.add(job)
        await session.commit()

    async with test_session_factory() as session:
        query = select(Document).where(Document.source_url == "https://example.com/article")
        result = await session.execute(query)
        stored_doc = result.scalar_one()
        assert stored_doc.title == "Article"
        assert stored_doc.deleted_at is None

        job_query = select(IngestionJob).where(IngestionJob.document_id == stored_doc.id)
        job_result = await session.execute(job_query)
        stored_job = job_result.scalar_one()
        assert stored_job.status == JobStatus.PENDING.value
        assert stored_job.progress_percentage == 0

    await test_engine.dispose()


def test_batch_job_status_enum_values():
    """Verify BatchJobStatus enum defines expected lifecycle stages."""
    from app.models.job import BatchJobStatus

    assert BatchJobStatus.PENDING.value == "PENDING"
    assert BatchJobStatus.PROCESSING.value == "PROCESSING"
    assert BatchJobStatus.COMPLETED.value == "COMPLETED"
    assert BatchJobStatus.PARTIALLY_FAILED.value == "PARTIALLY_FAILED"
    assert BatchJobStatus.FAILED.value == "FAILED"


def test_batch_ingestion_job_instantiation_defaults():
    """Verify BatchIngestionJob initializes with default fields and empty lists."""
    from app.models import BatchIngestionJob, BatchJobStatus

    batch = BatchIngestionJob()

    assert isinstance(batch.id, UUID)
    assert batch.status == BatchJobStatus.PENDING.value
    assert batch.total_count == 0
    assert batch.accepted_count == 0
    assert batch.skipped_count == 0
    assert batch.skipped_details == []
    assert isinstance(batch.created_at, datetime)
    assert batch.finished_at is None


def test_batch_ingestion_job_explicit_fields():
    """Verify BatchIngestionJob stores explicit counts, status, and skipped details."""
    from app.models import BatchIngestionJob, BatchJobStatus

    fixed_id = uuid4()
    finished = datetime.now()
    skipped = [{"url": "https://example.com/skipped", "reason": "already_ingested"}]

    batch = BatchIngestionJob(
        id=fixed_id,
        status=BatchJobStatus.COMPLETED.value,
        total_count=5,
        accepted_count=4,
        skipped_count=1,
        skipped_details=skipped,
        finished_at=finished,
    )

    assert batch.id == fixed_id
    assert batch.status == "COMPLETED"
    assert batch.total_count == 5
    assert batch.accepted_count == 4
    assert batch.skipped_count == 1
    assert batch.skipped_details == skipped
    assert batch.finished_at == finished


def test_ingestion_job_with_batch_id():
    """Verify IngestionJob accepts an optional batch_id."""
    from app.models import IngestionJob

    doc_id = uuid4()
    batch_id = uuid4()
    job = IngestionJob(document_id=doc_id, batch_id=batch_id)

    assert job.batch_id == batch_id


def test_batch_and_job_relationship():
    """Verify relationship between BatchIngestionJob and IngestionJob in memory."""
    from app.models import BatchIngestionJob, IngestionJob

    batch = BatchIngestionJob()
    doc_id = uuid4()
    job = IngestionJob(document_id=doc_id, batch=batch)

    assert job.batch is batch


@pytest.mark.asyncio
async def test_batch_and_jobs_database_persistence():
    """Verify BatchIngestionJob and child IngestionJob persistence with relational integrity."""
    from app.models import BatchIngestionJob, BatchJobStatus, Document, IngestionJob

    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    test_session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    batch_id = uuid4()
    async with test_session_factory() as session:
        batch = BatchIngestionJob(
            id=batch_id,
            status=BatchJobStatus.PROCESSING.value,
            total_count=2,
            accepted_count=2,
            skipped_count=0,
            skipped_details=[],
        )
        session.add(batch)

        doc1 = Document(source_type="url", source_url="https://example.com/doc1")
        doc2 = Document(source_type="url", source_url="https://example.com/doc2")
        session.add_all([doc1, doc2])
        await session.flush()

        job1 = IngestionJob(document_id=doc1.id, batch_id=batch.id)
        job2 = IngestionJob(document_id=doc2.id, batch_id=batch.id)
        session.add_all([job1, job2])
        await session.commit()

    async with test_session_factory() as session:
        query = select(BatchIngestionJob).where(BatchIngestionJob.id == batch_id)
        result = await session.execute(query)
        stored_batch = result.scalar_one()
        assert stored_batch.total_count == 2
        assert stored_batch.status == BatchJobStatus.PROCESSING.value

        jobs_query = select(IngestionJob).where(IngestionJob.batch_id == batch_id)
        jobs_result = await session.execute(jobs_query)
        stored_jobs = jobs_result.scalars().all()
        assert len(stored_jobs) == 2

    await test_engine.dispose()


def test_datetime_columns_have_timezone_aware_types():
    """Verify that all datetime columns are configured with timezone=True for asyncpg."""
    from app.models import BatchIngestionJob, Document, IngestionJob

    assert Document.__table__.c.created_at.type.timezone is True
    assert Document.__table__.c.updated_at.type.timezone is True
    assert Document.__table__.c.deleted_at.type.timezone is True

    assert IngestionJob.__table__.c.created_at.type.timezone is True
    assert IngestionJob.__table__.c.finished_at.type.timezone is True

    assert BatchIngestionJob.__table__.c.created_at.type.timezone is True
    assert BatchIngestionJob.__table__.c.finished_at.type.timezone is True


@pytest.mark.asyncio
async def test_postgres_datetime_persistence_if_available():
    """Verify entity persistence with UTC datetimes in PostgreSQL when reachable."""
    from app.core.config import settings
    from scripts.check_env import check_tcp_port

    if not check_tcp_port(settings.postgres_host, settings.postgres_port):
        pytest.skip(f"PostgreSQL unreachable at {settings.postgres_host}:{settings.postgres_port}")

    from app.models import BatchIngestionJob, BatchJobStatus, Document, IngestionJob, JobStatus

    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        batch = BatchIngestionJob(
            id=uuid4(),
            status=BatchJobStatus.PENDING.value,
            total_count=1,
            accepted_count=1,
            skipped_count=0,
            skipped_details=[],
        )
        session.add(batch)

        doc = Document(
            source_type="url",
            source_url=f"https://example.com/test-pg-{uuid4()}",
        )
        session.add(doc)
        await session.flush()

        job = IngestionJob(
            document_id=doc.id,
            batch_id=batch.id,
            status=JobStatus.PENDING.value,
        )
        session.add(job)
        await session.flush()

        # Clean up within transaction rollback
        await session.rollback()

    await engine.dispose()
