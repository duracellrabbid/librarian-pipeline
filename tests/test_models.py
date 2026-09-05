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
    partial_index = next(
        (idx for idx in indices if idx.name == "uq_documents_active_source_url"), None
    )
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
