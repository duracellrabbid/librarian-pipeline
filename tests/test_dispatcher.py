"""Unit tests for task dispatcher protocol and implementations."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from app.core.dispatcher import TaskDispatcher
from app.core.exceptions import DispatcherError, PipelineError
from app.workers.dispatcher import ArqTaskDispatcher, get_redis_settings
from app.workers.tasks import (
    WorkerSettings,
    coerce_uuid,
    run_ingestion_pipeline,
    shutdown,
    startup,
)
from arq.connections import RedisSettings
from loguru import logger


def test_dispatcher_error_inheritance_and_attributes() -> None:
    """Test that DispatcherError inherits from PipelineError and stores attributes."""
    original = ConnectionError("Redis down")
    err = DispatcherError("Failed to enqueue job", job_id="12345", original_error=original)
    assert isinstance(err, PipelineError)
    assert str(err) == "Failed to enqueue job"
    assert err.job_id == "12345"
    assert err.original_error is original


def test_dispatcher_error_default_attributes() -> None:
    """Test DispatcherError defaults when optional attributes are not provided."""
    err = DispatcherError("Dispatch failed")
    assert isinstance(err, PipelineError)
    assert str(err) == "Dispatch failed"
    assert err.job_id is None
    assert err.original_error is None


def test_task_dispatcher_protocol_runtime_checkable() -> None:
    """Test that TaskDispatcher protocol can be checked with isinstance at runtime."""

    class ValidDispatcher:
        async def enqueue_ingestion_job(
            self,
            job_id: UUID,
            document_id: UUID,
            url: str,
        ) -> None:
            pass

    class InvalidDispatcher:
        pass

    assert issubclass(ValidDispatcher, TaskDispatcher)
    assert isinstance(ValidDispatcher(), TaskDispatcher)
    assert not issubclass(InvalidDispatcher, TaskDispatcher)
    assert not isinstance(InvalidDispatcher(), TaskDispatcher)


@pytest.mark.asyncio
async def test_arq_task_dispatcher_implements_protocol() -> None:
    """Test that ArqTaskDispatcher implements the TaskDispatcher protocol."""
    mock_pool = AsyncMock()
    dispatcher = ArqTaskDispatcher(pool=mock_pool)
    assert isinstance(dispatcher, TaskDispatcher)


@pytest.mark.asyncio
async def test_arq_task_dispatcher_enqueue_success() -> None:
    """Test successful job enqueueing with parameter serialization."""
    mock_pool = AsyncMock()
    dispatcher = ArqTaskDispatcher(pool=mock_pool)

    job_id = uuid4()
    doc_id = uuid4()
    url = "https://example.com/docs"

    await dispatcher.enqueue_ingestion_job(job_id=job_id, document_id=doc_id, url=url)

    mock_pool.enqueue_job.assert_awaited_once_with(
        "run_ingestion_pipeline",
        str(job_id),
        str(doc_id),
        url,
        _job_id=str(job_id),
    )


@pytest.mark.asyncio
async def test_arq_task_dispatcher_lazy_pool_creation() -> None:
    """Test that ArqTaskDispatcher lazily initializes the pool if not provided."""
    mock_pool = AsyncMock()
    with patch("app.workers.dispatcher.create_pool", AsyncMock(return_value=mock_pool)) as mock_create_pool:
        dispatcher = ArqTaskDispatcher()
        job_id = uuid4()
        doc_id = uuid4()
        url = "https://example.com/page"

        await dispatcher.enqueue_ingestion_job(job_id=job_id, document_id=doc_id, url=url)
        mock_create_pool.assert_awaited_once()
        mock_pool.enqueue_job.assert_awaited_once()

        # Second call should reuse existing pool
        await dispatcher.enqueue_ingestion_job(job_id=job_id, document_id=doc_id, url=url)
        assert mock_create_pool.await_count == 1


@pytest.mark.asyncio
async def test_arq_task_dispatcher_broker_failure_raises_dispatcher_error() -> None:
    """Test that broker failure raises a DispatcherError domain exception."""
    mock_pool = AsyncMock()
    mock_pool.enqueue_job.side_effect = ConnectionError("Broker unreachable")
    dispatcher = ArqTaskDispatcher(pool=mock_pool)

    job_id = uuid4()
    doc_id = uuid4()
    url = "https://example.com/fail"

    with pytest.raises(DispatcherError) as exc_info:
        await dispatcher.enqueue_ingestion_job(job_id=job_id, document_id=doc_id, url=url)

    err = exc_info.value
    assert "Broker unreachable" in str(err)
    assert err.job_id == str(job_id)
    assert isinstance(err.original_error, ConnectionError)


@pytest.mark.asyncio
async def test_arq_task_dispatcher_pool_creation_failure_raises_dispatcher_error() -> None:
    """Test that failure during lazy pool creation raises DispatcherError."""
    with patch(
        "app.workers.dispatcher.create_pool",
        AsyncMock(side_effect=ConnectionError("Redis down")),
    ):
        dispatcher = ArqTaskDispatcher()
        job_id = uuid4()
        doc_id = uuid4()

        with pytest.raises(DispatcherError) as exc_info:
            await dispatcher.enqueue_ingestion_job(job_id=job_id, document_id=doc_id, url="https://example.com")

        err = exc_info.value
        assert "Redis down" in str(err)
        assert err.job_id == str(job_id)
        assert isinstance(err.original_error, ConnectionError)


@pytest.mark.asyncio
async def test_arq_task_dispatcher_close() -> None:
    """Test closing dispatcher closes the underlying pool."""
    mock_pool = AsyncMock()
    dispatcher = ArqTaskDispatcher(pool=mock_pool)
    await dispatcher.close()
    mock_pool.close.assert_awaited_once()

    # Closing when no pool was created should be a no-op
    dispatcher_no_pool = ArqTaskDispatcher()
    await dispatcher_no_pool.close()


def test_worker_settings_configuration() -> None:
    """Test that WorkerSettings defines functions, redis_settings, and hooks."""
    assert run_ingestion_pipeline in WorkerSettings.functions
    assert isinstance(WorkerSettings.redis_settings, RedisSettings)
    assert WorkerSettings.on_startup is startup
    assert WorkerSettings.on_shutdown is shutdown


@pytest.mark.asyncio
async def test_worker_lifecycle_startup_and_shutdown() -> None:
    """Test worker startup and shutdown lifecycle hooks."""
    ctx: dict[str, object] = {}
    await startup(ctx)
    assert "settings" in ctx

    await shutdown(ctx)


@pytest.mark.asyncio
async def test_worker_lifecycle_startup_and_shutdown_with_vector_store() -> None:
    """Test worker startup initializes vector store and shutdown closes it."""
    mock_vector_store = AsyncMock()
    mock_vector_store.close = AsyncMock()

    patch_qdrant = patch(
        "app.services.vector_store.qdrant.QdrantVectorStore",
        return_value=mock_vector_store,
    )
    with patch_qdrant:
        ctx: dict[str, object] = {}
        await startup(ctx)
        assert "settings" in ctx
        assert ctx.get("vector_store") is mock_vector_store
        mock_vector_store.initialize_collection.assert_awaited_once()

        await shutdown(ctx)
        mock_vector_store.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_lifecycle_startup_handles_vector_store_error() -> None:
    """Test worker startup logs warning and proceeds if vector store initialization fails."""
    mock_vector_store = AsyncMock()
    mock_vector_store.initialize_collection.side_effect = Exception("Qdrant unreachable")

    patch_qdrant = patch(
        "app.services.vector_store.qdrant.QdrantVectorStore",
        return_value=mock_vector_store,
    )
    with patch_qdrant:
        ctx: dict[str, object] = {}
        await startup(ctx)
        assert "settings" in ctx
        assert "vector_store" not in ctx

        await shutdown(ctx)


@pytest.mark.asyncio
async def test_run_ingestion_pipeline_uses_vector_store_from_ctx() -> None:
    """Test run_ingestion_pipeline passes vector_store from ctx to IngestionPipelineService."""
    mock_service_instance = AsyncMock()
    mock_service_cls = MagicMock(return_value=mock_service_instance)
    mock_module = MagicMock(IngestionPipelineService=mock_service_cls)
    mock_vec = MagicMock()

    with patch.dict("sys.modules", {"app.services.pipeline": mock_module}):
        ctx: dict[str, object] = {"vector_store": mock_vec}
        job_id = uuid4()
        doc_id = uuid4()
        await run_ingestion_pipeline(ctx, job_id, doc_id, "https://example.com")
        mock_service_cls.assert_called_once_with(vector_store=mock_vec)


@pytest.mark.asyncio
async def test_run_ingestion_pipeline_with_ctx_service() -> None:
    """Test run_ingestion_pipeline delegates to pipeline_service in ctx."""
    mock_service = AsyncMock()
    ctx = {"pipeline_service": mock_service}

    job_id = uuid4()
    doc_id = uuid4()
    url = "https://example.com/article"

    # Pass as string IDs to test deserialization/coercion
    await run_ingestion_pipeline(ctx, str(job_id), str(doc_id), url)

    mock_service.run.assert_awaited_once_with(
        job_id=job_id,
        document_id=doc_id,
        url=url,
    )


@pytest.mark.asyncio
async def test_run_ingestion_pipeline_with_uuid_instances() -> None:
    """Test run_ingestion_pipeline handles already-instantiated UUID objects."""
    mock_service = AsyncMock()
    ctx = {"pipeline_service": mock_service}

    job_id = uuid4()
    doc_id = uuid4()
    url = "https://example.com/article"

    await run_ingestion_pipeline(ctx, job_id, doc_id, url)

    mock_service.run.assert_awaited_once_with(
        job_id=job_id,
        document_id=doc_id,
        url=url,
    )


@pytest.mark.asyncio
async def test_run_ingestion_pipeline_service_fallback_or_missing() -> None:
    """Test run_ingestion_pipeline behavior when no service is in ctx and import fails."""
    with patch.dict("sys.modules", {"app.services.pipeline": None}):
        ctx: dict[str, object] = {}
        job_id = uuid4()
        doc_id = uuid4()
        url = "https://example.com/article"

        # When app.services.pipeline.IngestionPipelineService does not exist or fails,
        # it should handle gracefully without crashing
        await run_ingestion_pipeline(ctx, job_id, doc_id, url)


def test_get_redis_settings_fallback_to_host_port() -> None:
    """Test get_redis_settings when redis_url is not specified."""
    mock_settings = MagicMock()
    mock_settings.redis_url = None
    mock_settings.redis_host = "custom-redis"
    mock_settings.redis_port = 6380
    res = get_redis_settings(mock_settings)
    assert res.host == "custom-redis"
    assert res.port == 6380


@pytest.mark.asyncio
async def test_run_ingestion_pipeline_instantiates_service_when_imported() -> None:
    """Test run_ingestion_pipeline instantiates IngestionPipelineService if imported."""
    mock_service_instance = AsyncMock()
    mock_service_cls = MagicMock(return_value=mock_service_instance)
    mock_module = MagicMock(IngestionPipelineService=mock_service_cls)

    with patch.dict("sys.modules", {"app.services.pipeline": mock_module}):
        ctx: dict[str, object] = {}
        job_id = uuid4()
        doc_id = uuid4()
        await run_ingestion_pipeline(ctx, job_id, doc_id, "https://example.com")
        mock_service_cls.assert_called_once()
        mock_service_instance.run.assert_awaited_once_with(
            job_id=job_id,
            document_id=doc_id,
            url="https://example.com",
        )


@pytest.mark.asyncio
async def test_run_ingestion_pipeline_instantiates_real_service() -> None:
    """Test run_ingestion_pipeline instantiates IngestionPipelineService directly."""
    with patch("app.services.pipeline.IngestionPipelineService.run", AsyncMock()) as mock_run:
        ctx: dict[str, object] = {}
        job_id = uuid4()
        doc_id = uuid4()
        await run_ingestion_pipeline(ctx, job_id, doc_id, "https://example.com")
        mock_run.assert_awaited_once_with(
            job_id=job_id,
            document_id=doc_id,
            url="https://example.com",
        )


def test_coerce_uuid() -> None:
    """Test coerce_uuid handles both string and UUID."""
    u = uuid4()
    assert coerce_uuid(u) is u
    assert coerce_uuid(str(u)) == u


def test_worker_settings_job_timeout() -> None:
    """Test WorkerSettings.job_timeout matches arq_job_timeout setting (900s)."""
    assert WorkerSettings.job_timeout == 900


@pytest.mark.asyncio
async def test_run_ingestion_pipeline_contextualizes_job_and_document_id() -> None:
    """Test that run_ingestion_pipeline binds job_id and document_id in Loguru extra."""
    captured_records: list[Any] = []
    sink_id = logger.add(lambda msg: captured_records.append(msg.record), level="DEBUG")
    job_id = uuid4()
    doc_id = uuid4()

    mock_service = AsyncMock()

    async def fake_run(*args: Any, **kwargs: Any) -> None:
        logger.info("Executing pipeline service run")

    mock_service.run.side_effect = fake_run
    ctx = {"pipeline_service": mock_service}

    try:
        await run_ingestion_pipeline(ctx, job_id, doc_id, "https://example.com")
        log = next(r for r in captured_records if r["message"] == "Executing pipeline service run")
        assert log["extra"].get("job_id") == str(job_id)
        assert log["extra"].get("document_id") == str(doc_id)
    finally:
        logger.remove(sink_id)


@pytest.mark.asyncio
async def test_run_ingestion_pipeline_fallback_warning_contextualized() -> None:
    """Test that fallback warning binds job_id and document_id in Loguru extra."""
    captured_records: list[Any] = []
    sink_id = logger.add(lambda msg: captured_records.append(msg.record), level="WARNING")
    job_id = uuid4()
    doc_id = uuid4()

    try:
        with patch.dict("sys.modules", {"app.services.pipeline": None}):
            ctx: dict[str, object] = {}
            await run_ingestion_pipeline(ctx, job_id, doc_id, "https://example.com")

        log = next(r for r in captured_records if "IngestionPipelineService not available" in r["message"])
        assert f"skipping pipeline run for job {job_id}" in log["message"]
        assert log["extra"].get("job_id") == str(job_id)
        assert log["extra"].get("document_id") == str(doc_id)
    finally:
        logger.remove(sink_id)


@pytest.mark.asyncio
async def test_worker_startup_and_shutdown_logs_with_loguru() -> None:
    """Test that worker startup and shutdown emit logs via Loguru."""
    captured_records: list[Any] = []
    sink_id = logger.add(lambda msg: captured_records.append(msg.record), level="INFO")
    ctx: dict[str, object] = {}

    try:
        await startup(ctx)
        await shutdown(ctx)

        startup_logs = [r for r in captured_records if "ARQ worker started" in r["message"]]
        shutdown_logs = [r for r in captured_records if "ARQ worker shutting down" in r["message"]]

        assert len(startup_logs) == 1
        assert len(shutdown_logs) == 1
    finally:
        logger.remove(sink_id)


@pytest.mark.asyncio
async def test_worker_startup_vector_store_error_logs_warning_with_loguru() -> None:
    """Test that vector store initialization failure in startup logs via Loguru."""
    captured_records: list[Any] = []
    sink_id = logger.add(lambda msg: captured_records.append(msg.record), level="WARNING")
    ctx: dict[str, object] = {}

    mock_vector_store = AsyncMock()
    mock_vector_store.initialize_collection.side_effect = RuntimeError("Qdrant connection lost")

    try:
        with patch(
            "app.services.vector_store.qdrant.QdrantVectorStore",
            return_value=mock_vector_store,
        ):
            await startup(ctx)

        warning_logs = [
            r for r in captured_records if "Could not initialize Qdrant vector store in worker startup" in r["message"]
        ]
        assert len(warning_logs) == 1
        assert "Qdrant connection lost" in warning_logs[0]["message"]
    finally:
        logger.remove(sink_id)
