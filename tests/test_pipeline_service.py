"""Unit tests for IngestionPipelineService."""

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from app.core.exceptions import (
    EmbeddingError,
    ExtractionError,
    VectorStoreError,
)
from app.models.document import Document
from app.models.job import IngestionJob, JobStatus
from app.services.chunkers.base import DocumentChunk
from app.services.extractors.base import ExtractedDocument
from app.services.pipeline import IngestionPipelineService
from app.services.repository import DocumentNotFoundError, update_document_metadata
from loguru import logger


@pytest.fixture
def mock_extractor() -> AsyncMock:
    """Fixture providing a mock BaseExtractor."""
    extractor = AsyncMock()
    extractor.extract.return_value = ExtractedDocument(
        content="# Sample Document\n\nThis is test content.",
        title="Sample Title",
        source_url="https://en.wikipedia.org/wiki/test",
        metadata={"lang": "en"},
    )
    return extractor


@pytest.fixture
def mock_chunker() -> MagicMock:
    """Fixture providing a mock BaseChunker."""
    chunker = MagicMock()
    chunker.chunk.return_value = [
        DocumentChunk(
            chunk_index=0,
            text="Sample Document This is test content.",
            char_count=37,
            token_count=9,
            metadata={"header": "Sample Document"},
        )
    ]
    return chunker


@pytest.fixture
def mock_embedding_client() -> AsyncMock:
    """Fixture providing a mock BaseEmbeddingClient."""
    client = AsyncMock()
    client.embed_batch.return_value = [[0.1] * 1024]
    return client


@pytest.fixture
def mock_vector_store() -> AsyncMock:
    """Fixture providing a mock BaseVectorStore."""
    store = AsyncMock()
    store.upsert_chunks.return_value = 1
    return store


@pytest.fixture
def mock_session() -> AsyncMock:
    """Fixture providing a mock AsyncSession with job and document tracking."""
    session = AsyncMock()
    return session


@pytest.fixture
def session_factory(mock_session: AsyncMock):
    """Fixture providing an async session context manager factory."""

    @asynccontextmanager
    async def _factory():
        yield mock_session

    return _factory


def test_pipeline_service_default_initialization() -> None:
    """Test initializing IngestionPipelineService with default components."""
    cls_path = "app.services.pipeline.IngestionPipelineService"
    with (
        patch(f"{cls_path}._default_extractor") as mock_ext,
        patch(f"{cls_path}._default_chunker") as mock_chk,
        patch(f"{cls_path}._default_embedding_client") as mock_emb,
        patch(f"{cls_path}._default_vector_store") as mock_vec,
    ):
        mock_ext.return_value = MagicMock()
        mock_chk.return_value = MagicMock()
        mock_emb.return_value = MagicMock()
        mock_vec.return_value = MagicMock()

        service = IngestionPipelineService()
        assert service.extractor is mock_ext.return_value
        assert service.chunker is mock_chk.return_value
        assert service.embedding_client is mock_emb.return_value
        assert service.vector_store is mock_vec.return_value
        assert service.session_factory is not None


def test_default_resolvers() -> None:
    """Test default resolver static methods."""
    with patch("app.services.extractors.web.Crawl4AIExtractor") as mock_ext:
        assert IngestionPipelineService._default_extractor() is mock_ext.return_value
    with patch("app.services.chunkers.hybrid.HybridMarkdownChunker") as mock_chk:
        assert IngestionPipelineService._default_chunker() is mock_chk.return_value
    with patch("app.services.embeddings.ollama.OllamaEmbeddingClient") as mock_emb:
        assert IngestionPipelineService._default_embedding_client() is mock_emb.return_value
    with patch("app.services.vector_store.qdrant.QdrantVectorStore") as mock_vec:
        assert IngestionPipelineService._default_vector_store() is mock_vec.return_value


def test_pipeline_service_custom_initialization(
    mock_extractor: AsyncMock,
    mock_chunker: MagicMock,
    mock_embedding_client: AsyncMock,
    mock_vector_store: AsyncMock,
    session_factory,
) -> None:
    """Test initializing IngestionPipelineService with custom injected components."""
    service = IngestionPipelineService(
        extractor=mock_extractor,
        chunker=mock_chunker,
        embedding_client=mock_embedding_client,
        vector_store=mock_vector_store,
        session_factory=session_factory,
    )
    assert service.extractor is mock_extractor
    assert service.chunker is mock_chunker
    assert service.embedding_client is mock_embedding_client
    assert service.vector_store is mock_vector_store
    assert service.session_factory is session_factory


@pytest.mark.asyncio
async def test_get_session_plain_session_object() -> None:
    """Test _get_session when session_factory returns a bare session without __aenter__."""
    mock_session_bare = MagicMock(spec=[])
    service = IngestionPipelineService(
        session_factory=lambda: mock_session_bare,
        extractor=MagicMock(),
        chunker=MagicMock(),
        embedding_client=MagicMock(),
        vector_store=MagicMock(),
    )
    async with service._get_session() as s:
        assert s is mock_session_bare


@pytest.mark.asyncio
async def test_pipeline_service_successful_end_to_end(
    mock_extractor: AsyncMock,
    mock_chunker: MagicMock,
    mock_embedding_client: AsyncMock,
    mock_vector_store: AsyncMock,
    session_factory,
    mock_session: AsyncMock,
) -> None:
    """Test complete successful pipeline progression through all stages."""
    job_id = uuid4()
    doc_id = uuid4()
    url = "https://en.wikipedia.org/wiki/Test"

    job = IngestionJob(
        id=job_id,
        document_id=doc_id,
        status=JobStatus.PENDING.value,
        progress_percentage=0,
    )
    doc = Document(
        id=doc_id,
        source_type="url",
        source_url=url,
    )

    def execute_side_effect(stmt):
        mock_result = MagicMock()
        stmt_str = str(stmt)
        if "ingestion_jobs" in stmt_str:
            mock_result.scalars.return_value.first.return_value = job
        elif "documents" in stmt_str:
            mock_result.scalars.return_value.first.return_value = doc
        return mock_result

    mock_session.execute.side_effect = execute_side_effect

    service = IngestionPipelineService(
        extractor=mock_extractor,
        chunker=mock_chunker,
        embedding_client=mock_embedding_client,
        vector_store=mock_vector_store,
        session_factory=session_factory,
    )

    await service.run(job_id=job_id, document_id=doc_id, url=url)

    # Verify component interactions
    mock_extractor.extract.assert_awaited_once_with(url)
    mock_chunker.chunk.assert_called_once()
    mock_embedding_client.embed_batch.assert_awaited_once_with(["Sample Document This is test content."])
    mock_vector_store.initialize_collection.assert_awaited_once()
    mock_vector_store.upsert_chunks.assert_awaited_once()

    # Verify Document updated
    assert doc.title == "Sample Title"
    assert doc.chunk_count == 1
    assert doc.content_hash is not None

    # Verify Job reached terminal INDEXED status
    assert job.status == JobStatus.INDEXED.value
    assert job.progress_percentage == 100
    assert job.finished_at is not None


@pytest.mark.asyncio
async def test_pipeline_service_extraction_failure(
    mock_extractor: AsyncMock,
    mock_chunker: MagicMock,
    mock_embedding_client: AsyncMock,
    mock_vector_store: AsyncMock,
    session_factory,
    mock_session: AsyncMock,
) -> None:
    """Test error handling when extraction fails."""
    job_id = uuid4()
    doc_id = uuid4()
    url = "https://en.wikipedia.org/wiki/Fail"

    job = IngestionJob(
        id=job_id,
        document_id=doc_id,
        status=JobStatus.PENDING.value,
        progress_percentage=0,
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = job
    mock_session.execute.return_value = mock_result

    mock_extractor.extract.side_effect = ExtractionError("Extraction timed out", url=url)

    service = IngestionPipelineService(
        extractor=mock_extractor,
        chunker=mock_chunker,
        embedding_client=mock_embedding_client,
        vector_store=mock_vector_store,
        session_factory=session_factory,
    )

    # Must terminate cleanly without re-raising
    await service.run(job_id=job_id, document_id=doc_id, url=url)

    assert job.status == JobStatus.FAILED.value
    assert "Extraction timed out" in (job.error_message or "")
    mock_chunker.chunk.assert_not_called()
    mock_embedding_client.embed_batch.assert_not_called()
    mock_vector_store.upsert_chunks.assert_not_called()


@pytest.mark.asyncio
async def test_pipeline_service_chunking_failure(
    mock_extractor: AsyncMock,
    mock_chunker: MagicMock,
    mock_embedding_client: AsyncMock,
    mock_vector_store: AsyncMock,
    session_factory,
    mock_session: AsyncMock,
) -> None:
    """Test error handling when chunking fails."""
    job_id = uuid4()
    doc_id = uuid4()
    url = "https://en.wikipedia.org/wiki/ChunkFail"

    job = IngestionJob(
        id=job_id,
        document_id=doc_id,
        status=JobStatus.PENDING.value,
        progress_percentage=0,
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = job
    mock_session.execute.return_value = mock_result

    mock_chunker.chunk.side_effect = ValueError("Corrupt markdown structure")

    service = IngestionPipelineService(
        extractor=mock_extractor,
        chunker=mock_chunker,
        embedding_client=mock_embedding_client,
        vector_store=mock_vector_store,
        session_factory=session_factory,
    )

    await service.run(job_id=job_id, document_id=doc_id, url=url)

    assert job.status == JobStatus.FAILED.value
    assert "Corrupt markdown structure" in (job.error_message or "")
    mock_embedding_client.embed_batch.assert_not_called()
    mock_vector_store.upsert_chunks.assert_not_called()


@pytest.mark.asyncio
async def test_pipeline_service_embedding_failure(
    mock_extractor: AsyncMock,
    mock_chunker: MagicMock,
    mock_embedding_client: AsyncMock,
    mock_vector_store: AsyncMock,
    session_factory,
    mock_session: AsyncMock,
) -> None:
    """Test error handling when embedding generation fails."""
    job_id = uuid4()
    doc_id = uuid4()
    url = "https://en.wikipedia.org/wiki/EmbedFail"

    job = IngestionJob(
        id=job_id,
        document_id=doc_id,
        status=JobStatus.PENDING.value,
        progress_percentage=0,
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = job
    mock_session.execute.return_value = mock_result

    mock_embedding_client.embed_batch.side_effect = EmbeddingError("Ollama offline")

    service = IngestionPipelineService(
        extractor=mock_extractor,
        chunker=mock_chunker,
        embedding_client=mock_embedding_client,
        vector_store=mock_vector_store,
        session_factory=session_factory,
    )

    await service.run(job_id=job_id, document_id=doc_id, url=url)

    assert job.status == JobStatus.FAILED.value
    assert "Ollama offline" in (job.error_message or "")
    mock_vector_store.upsert_chunks.assert_not_called()


@pytest.mark.asyncio
async def test_pipeline_service_vector_store_failure(
    mock_extractor: AsyncMock,
    mock_chunker: MagicMock,
    mock_embedding_client: AsyncMock,
    mock_vector_store: AsyncMock,
    session_factory,
    mock_session: AsyncMock,
) -> None:
    """Test error handling when vector storage upsert fails."""
    job_id = uuid4()
    doc_id = uuid4()
    url = "https://en.wikipedia.org/wiki/QdrantFail"

    job = IngestionJob(
        id=job_id,
        document_id=doc_id,
        status=JobStatus.PENDING.value,
        progress_percentage=0,
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = job
    mock_session.execute.return_value = mock_result

    mock_vector_store.upsert_chunks.side_effect = VectorStoreError("Qdrant connection dropped")

    service = IngestionPipelineService(
        extractor=mock_extractor,
        chunker=mock_chunker,
        embedding_client=mock_embedding_client,
        vector_store=mock_vector_store,
        session_factory=session_factory,
    )

    await service.run(job_id=job_id, document_id=doc_id, url=url)

    assert job.status == JobStatus.FAILED.value
    assert "Qdrant connection dropped" in (job.error_message or "")


@pytest.mark.asyncio
async def test_pipeline_run_vector_store_init_error_transitions_to_failed(
    mock_extractor: AsyncMock,
    mock_chunker: MagicMock,
    mock_embedding_client: AsyncMock,
    mock_vector_store: AsyncMock,
    mock_session: AsyncMock,
    session_factory,
) -> None:
    """Test that failure during vector_store.initialize_collection marks job FAILED."""
    job_id = uuid4()
    doc_id = uuid4()
    url = "https://en.wikipedia.org/wiki/FailVecInit"

    job = IngestionJob(
        id=job_id,
        document_id=doc_id,
        status=JobStatus.PENDING.value,
        progress_percentage=0,
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = job
    mock_session.execute.return_value = mock_result

    mock_vector_store.initialize_collection.side_effect = VectorStoreError("Qdrant init failed")

    service = IngestionPipelineService(
        extractor=mock_extractor,
        chunker=mock_chunker,
        embedding_client=mock_embedding_client,
        vector_store=mock_vector_store,
        session_factory=session_factory,
    )

    await service.run(job_id=job_id, document_id=doc_id, url=url)

    assert job.status == JobStatus.FAILED.value
    assert "Qdrant init failed" in (job.error_message or "")
    mock_vector_store.upsert_chunks.assert_not_called()


@pytest.mark.asyncio
async def test_pipeline_service_empty_chunks(
    mock_extractor: AsyncMock,
    mock_chunker: MagicMock,
    mock_embedding_client: AsyncMock,
    mock_vector_store: AsyncMock,
    session_factory,
    mock_session: AsyncMock,
) -> None:
    """Test pipeline execution when document yields zero chunks."""
    job_id = uuid4()
    doc_id = uuid4()
    url = "https://en.wikipedia.org/wiki/Empty"

    job = IngestionJob(
        id=job_id,
        document_id=doc_id,
        status=JobStatus.PENDING.value,
        progress_percentage=0,
    )
    doc = Document(
        id=doc_id,
        source_type="url",
        source_url=url,
    )

    def execute_side_effect(stmt):
        mock_result = MagicMock()
        stmt_str = str(stmt)
        if "ingestion_jobs" in stmt_str:
            mock_result.scalars.return_value.first.return_value = job
        elif "documents" in stmt_str:
            mock_result.scalars.return_value.first.return_value = doc
        return mock_result

    mock_session.execute.side_effect = execute_side_effect
    mock_chunker.chunk.return_value = []

    service = IngestionPipelineService(
        extractor=mock_extractor,
        chunker=mock_chunker,
        embedding_client=mock_embedding_client,
        vector_store=mock_vector_store,
        session_factory=session_factory,
    )

    await service.run(job_id=job_id, document_id=doc_id, url=url)

    mock_embedding_client.embed_batch.assert_not_called()
    mock_vector_store.upsert_chunks.assert_not_called()
    assert doc.chunk_count == 0
    assert job.status == JobStatus.INDEXED.value
    assert job.progress_percentage == 100


@pytest.mark.asyncio
async def test_pipeline_service_failure_db_error_handling(
    mock_extractor: AsyncMock,
    session_factory,
    mock_session: AsyncMock,
) -> None:
    """Test error handling when logging failure itself encounters a database error."""
    job_id = uuid4()
    doc_id = uuid4()
    mock_extractor.extract.side_effect = Exception("Original error")
    mock_session.execute.side_effect = Exception("DB down")

    service = IngestionPipelineService(
        extractor=mock_extractor,
        session_factory=session_factory,
    )
    # Should not raise exception
    await service.run(job_id=job_id, document_id=doc_id, url="https://en.wikipedia.org/wiki/DbError")


@pytest.mark.asyncio
async def test_update_document_metadata_success(mock_session: AsyncMock) -> None:
    """Test update_document_metadata helper successfully updates document."""
    doc_id = uuid4()
    doc = Document(
        id=doc_id,
        source_type="url",
        source_url="https://en.wikipedia.org/wiki/Doc",
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = doc
    mock_session.execute.return_value = mock_result

    updated = await update_document_metadata(
        session=mock_session,
        document_id=doc_id,
        title="New Title",
        chunk_count=5,
        content_hash="abc123hash",
    )

    assert updated.title == "New Title"
    assert updated.chunk_count == 5
    assert updated.content_hash == "abc123hash"
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_document_metadata_not_found(mock_session: AsyncMock) -> None:
    """Test update_document_metadata raises DocumentNotFoundError if doc missing."""
    doc_id = uuid4()

    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_session.execute.return_value = mock_result

    with pytest.raises(DocumentNotFoundError):
        await update_document_metadata(
            session=mock_session,
            document_id=doc_id,
            title="Title",
        )


@pytest.mark.asyncio
async def test_pipeline_service_task_cancelled_handling(
    mock_extractor: AsyncMock,
    mock_chunker: MagicMock,
    mock_embedding_client: AsyncMock,
    mock_vector_store: AsyncMock,
    session_factory,
    mock_session: AsyncMock,
) -> None:
    """Test that asyncio.CancelledError transitions the job to FAILED and re-raises."""
    import asyncio

    job_id = uuid4()
    doc_id = uuid4()
    url = "https://en.wikipedia.org/wiki/Timeout"

    job = IngestionJob(
        id=job_id,
        document_id=doc_id,
        status=JobStatus.EMBEDDING.value,
        progress_percentage=70,
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = job
    mock_session.execute.return_value = mock_result

    # Simulate cancellation during embedding
    mock_embedding_client.embed_batch.side_effect = asyncio.CancelledError()

    service = IngestionPipelineService(
        extractor=mock_extractor,
        chunker=mock_chunker,
        embedding_client=mock_embedding_client,
        vector_store=mock_vector_store,
        session_factory=session_factory,
    )

    with pytest.raises(asyncio.CancelledError):
        await service.run(job_id=job_id, document_id=doc_id, url=url)

    assert job.status == JobStatus.FAILED.value
    assert "Job timed out or was cancelled" in (job.error_message or "")


@pytest.mark.asyncio
async def test_pipeline_service_run_contextualizes_job_and_document_id(
    mock_extractor: AsyncMock,
    mock_chunker: MagicMock,
    mock_embedding_client: AsyncMock,
    mock_vector_store: AsyncMock,
    session_factory,
    mock_session: AsyncMock,
) -> None:
    """Test that IngestionPipelineService.run contextualizes logger with job_id and document_id."""
    job_id = uuid4()
    doc_id = uuid4()
    url = "https://en.wikipedia.org/wiki/TestContext"

    captured_records: list[Any] = []
    sink_id = logger.add(lambda msg: captured_records.append(msg.record), level="INFO")

    async def extract_and_log(_url: str) -> ExtractedDocument:
        logger.info("Inside extraction step")
        return ExtractedDocument(
            content="# Content",
            title="Title",
            source_url=_url,
            metadata={},
        )

    mock_extractor.extract.side_effect = extract_and_log

    job = IngestionJob(
        id=job_id,
        document_id=doc_id,
        status=JobStatus.PENDING.value,
        progress_percentage=0,
    )
    doc = Document(id=doc_id, source_type="url", source_url=url)

    def execute_side_effect(stmt):
        mock_result = MagicMock()
        stmt_str = str(stmt)
        if "ingestion_jobs" in stmt_str:
            mock_result.scalars.return_value.first.return_value = job
        elif "documents" in stmt_str:
            mock_result.scalars.return_value.first.return_value = doc
        return mock_result

    mock_session.execute.side_effect = execute_side_effect

    service = IngestionPipelineService(
        extractor=mock_extractor,
        chunker=mock_chunker,
        embedding_client=mock_embedding_client,
        vector_store=mock_vector_store,
        session_factory=session_factory,
    )

    try:
        await service.run(job_id=job_id, document_id=doc_id, url=url)

        extract_log = next(r for r in captured_records if r["message"] == "Inside extraction step")
        assert extract_log["extra"].get("job_id") == str(job_id)
        assert extract_log["extra"].get("document_id") == str(doc_id)
    finally:
        logger.remove(sink_id)


@pytest.mark.asyncio
async def test_pipeline_service_failure_logs_exception_with_loguru(
    mock_extractor: AsyncMock,
    mock_chunker: MagicMock,
    mock_embedding_client: AsyncMock,
    mock_vector_store: AsyncMock,
    session_factory,
    mock_session: AsyncMock,
) -> None:
    """Test that pipeline execution failure logs exception via Loguru with extra context."""
    job_id = uuid4()
    doc_id = uuid4()
    url = "https://en.wikipedia.org/wiki/FailLog"

    captured_records: list[Any] = []
    sink_id = logger.add(lambda msg: captured_records.append(msg.record), level="ERROR")

    job = IngestionJob(
        id=job_id,
        document_id=doc_id,
        status=JobStatus.PENDING.value,
        progress_percentage=0,
    )
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = job
    mock_session.execute.return_value = mock_result

    mock_extractor.extract.side_effect = ExtractionError("Extraction broke", url=url)

    service = IngestionPipelineService(
        extractor=mock_extractor,
        chunker=mock_chunker,
        embedding_client=mock_embedding_client,
        vector_store=mock_vector_store,
        session_factory=session_factory,
    )

    try:
        await service.run(job_id=job_id, document_id=doc_id, url=url)

        err_log = next(r for r in captured_records if f"Ingestion pipeline failed for job {job_id}:" in r["message"])
        assert err_log["extra"].get("job_id") == str(job_id)
        assert err_log["extra"].get("document_id") == str(doc_id)
        assert err_log["exception"] is not None
    finally:
        logger.remove(sink_id)


@pytest.mark.asyncio
async def test_pipeline_service_timeout_logs_warning_with_loguru(
    mock_extractor: AsyncMock,
    mock_chunker: MagicMock,
    mock_embedding_client: AsyncMock,
    mock_vector_store: AsyncMock,
    session_factory,
    mock_session: AsyncMock,
) -> None:
    """Test that cancellation or timeout logs warning via Loguru with extra context."""
    import asyncio

    job_id = uuid4()
    doc_id = uuid4()
    url = "https://en.wikipedia.org/wiki/CancelLog"

    captured_records: list[Any] = []
    sink_id = logger.add(lambda msg: captured_records.append(msg.record), level="WARNING")

    job = IngestionJob(
        id=job_id,
        document_id=doc_id,
        status=JobStatus.PENDING.value,
        progress_percentage=0,
    )
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = job
    mock_session.execute.return_value = mock_result

    mock_extractor.extract.side_effect = asyncio.CancelledError()

    service = IngestionPipelineService(
        extractor=mock_extractor,
        chunker=mock_chunker,
        embedding_client=mock_embedding_client,
        vector_store=mock_vector_store,
        session_factory=session_factory,
    )

    try:
        with pytest.raises(asyncio.CancelledError):
            await service.run(job_id=job_id, document_id=doc_id, url=url)

        warn_log = next(
            r for r in captured_records if f"Ingestion pipeline cancelled or timed out for job {job_id}" in r["message"]
        )
        assert warn_log["extra"].get("job_id") == str(job_id)
        assert warn_log["extra"].get("document_id") == str(doc_id)
    finally:
        logger.remove(sink_id)


@pytest.mark.asyncio
async def test_pipeline_service_db_failure_in_handle_failure_logs_exception(
    mock_extractor: AsyncMock,
    session_factory,
    mock_session: AsyncMock,
) -> None:
    """Test that db exception in _handle_failure logs via Loguru with extra context."""
    job_id = uuid4()
    doc_id = uuid4()
    url = "https://en.wikipedia.org/wiki/DbFailLog"

    captured_records: list[Any] = []
    sink_id = logger.add(lambda msg: captured_records.append(msg.record), level="ERROR")

    mock_extractor.extract.side_effect = Exception("Original error")
    mock_session.execute.side_effect = RuntimeError("Database crash")

    service = IngestionPipelineService(
        extractor=mock_extractor,
        session_factory=session_factory,
    )

    try:
        await service.run(job_id=job_id, document_id=doc_id, url=url)

        db_err_log = next(
            r
            for r in captured_records
            if f"Failed to update FAILED status for job {job_id}: Database crash" in r["message"]
        )
        assert db_err_log["extra"].get("job_id") == str(job_id)
        assert db_err_log["extra"].get("document_id") == str(doc_id)
        assert db_err_log["exception"] is not None
    finally:
        logger.remove(sink_id)


@pytest.mark.asyncio
async def test_pipeline_service_rejects_unallowed_url_before_extraction(
    mock_extractor: AsyncMock,
    mock_chunker: MagicMock,
    mock_embedding_client: AsyncMock,
    mock_vector_store: AsyncMock,
    session_factory,
    mock_session: AsyncMock,
) -> None:
    """Test defense-in-depth: unallowed domain fails before calling extractor."""
    job_id = uuid4()
    doc_id = uuid4()
    url = "https://malicious-site.com/exploit"

    job = IngestionJob(
        id=job_id,
        document_id=doc_id,
        status=JobStatus.PENDING.value,
        progress_percentage=0,
    )
    doc = Document(id=doc_id, source_type="url", source_url=url)

    def execute_side_effect(stmt):
        mock_result = MagicMock()
        stmt_str = str(stmt)
        if "ingestion_jobs" in stmt_str:
            mock_result.scalars.return_value.first.return_value = job
        elif "documents" in stmt_str:
            mock_result.scalars.return_value.first.return_value = doc
        return mock_result

    mock_session.execute.side_effect = execute_side_effect

    service = IngestionPipelineService(
        extractor=mock_extractor,
        chunker=mock_chunker,
        embedding_client=mock_embedding_client,
        vector_store=mock_vector_store,
        session_factory=session_factory,
    )

    await service.run(job_id=job_id, document_id=doc_id, url=url)

    assert job.status == JobStatus.FAILED.value
    assert "URL domain is not allowed" in (job.error_message or "")
    mock_extractor.extract.assert_not_called()
    mock_chunker.chunk.assert_not_called()
    mock_embedding_client.embed_batch.assert_not_called()
    mock_vector_store.upsert_chunks.assert_not_called()


@pytest.mark.asyncio
async def test_pipeline_service_rejects_subdomain_ssrf_attempt_before_extraction(
    mock_extractor: AsyncMock,
    mock_chunker: MagicMock,
    mock_embedding_client: AsyncMock,
    mock_vector_store: AsyncMock,
    session_factory,
    mock_session: AsyncMock,
) -> None:
    """Test defense-in-depth: deceptive subdomain prefix fails before calling extractor."""
    job_id = uuid4()
    doc_id = uuid4()
    url = "https://en.wikipedia.org.attacker.com/wiki/Test"

    job = IngestionJob(
        id=job_id,
        document_id=doc_id,
        status=JobStatus.PENDING.value,
        progress_percentage=0,
    )
    doc = Document(id=doc_id, source_type="url", source_url=url)

    def execute_side_effect(stmt):
        mock_result = MagicMock()
        stmt_str = str(stmt)
        if "ingestion_jobs" in stmt_str:
            mock_result.scalars.return_value.first.return_value = job
        elif "documents" in stmt_str:
            mock_result.scalars.return_value.first.return_value = doc
        return mock_result

    mock_session.execute.side_effect = execute_side_effect

    service = IngestionPipelineService(
        extractor=mock_extractor,
        chunker=mock_chunker,
        embedding_client=mock_embedding_client,
        vector_store=mock_vector_store,
        session_factory=session_factory,
    )

    await service.run(job_id=job_id, document_id=doc_id, url=url)

    assert job.status == JobStatus.FAILED.value
    assert "URL domain is not allowed" in (job.error_message or "")
    mock_extractor.extract.assert_not_called()


@pytest.mark.asyncio
async def test_pipeline_service_custom_allowed_domains(
    mock_extractor: AsyncMock,
    mock_chunker: MagicMock,
    mock_embedding_client: AsyncMock,
    mock_vector_store: AsyncMock,
    session_factory,
    mock_session: AsyncMock,
) -> None:
    """Test custom allowed_domains parameter passed to IngestionPipelineService."""
    job_id = uuid4()
    doc_id = uuid4()
    url = "https://custom.allowed.domain/page"

    job = IngestionJob(
        id=job_id,
        document_id=doc_id,
        status=JobStatus.PENDING.value,
        progress_percentage=0,
    )
    doc = Document(id=doc_id, source_type="url", source_url=url)

    def execute_side_effect(stmt):
        mock_result = MagicMock()
        stmt_str = str(stmt)
        if "ingestion_jobs" in stmt_str:
            mock_result.scalars.return_value.first.return_value = job
        elif "documents" in stmt_str:
            mock_result.scalars.return_value.first.return_value = doc
        return mock_result

    mock_session.execute.side_effect = execute_side_effect

    service = IngestionPipelineService(
        extractor=mock_extractor,
        chunker=mock_chunker,
        embedding_client=mock_embedding_client,
        vector_store=mock_vector_store,
        session_factory=session_factory,
        allowed_domains=["https://custom.allowed.domain"],
    )

    await service.run(job_id=job_id, document_id=doc_id, url=url)

    assert job.status == JobStatus.INDEXED.value
    mock_extractor.extract.assert_awaited_once_with(url)
