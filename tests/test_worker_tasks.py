"""Unit and integration tests for worker tasks and rate limiter injection."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from app.services.extractors.limiter import InProcessDomainRateLimiter
from app.services.pipeline import IngestionPipelineService
from app.workers.tasks import run_ingestion_pipeline, startup


@pytest.mark.asyncio
async def test_worker_startup_initializes_rate_limiter() -> None:
    """Test that worker startup initializes InProcessDomainRateLimiter in worker context."""
    ctx: dict[str, object] = {}
    with patch("app.services.vector_store.qdrant.QdrantVectorStore.initialize_collection", AsyncMock()):
        await startup(ctx)

    assert "rate_limiter" in ctx
    limiter = ctx["rate_limiter"]
    assert isinstance(limiter, InProcessDomainRateLimiter)
    assert limiter.max_concurrency == 2


@pytest.mark.asyncio
async def test_worker_startup_rate_limiter_initialization_failure() -> None:
    """Test that rate limiter initialization failure during startup is logged and does not crash."""
    ctx: dict[str, object] = {}
    with (
        patch(
            "app.services.extractors.limiter.InProcessDomainRateLimiter",
            side_effect=Exception("Limiter failed"),
        ),
        patch("app.services.vector_store.qdrant.QdrantVectorStore.initialize_collection", AsyncMock()),
    ):
        await startup(ctx)

    assert "rate_limiter" not in ctx
    assert "settings" in ctx


@pytest.mark.asyncio
async def test_run_ingestion_pipeline_injects_rate_limiter_from_ctx() -> None:
    """Test that run_ingestion_pipeline passes rate_limiter from worker context to IngestionPipelineService."""
    mock_service_instance = AsyncMock()
    mock_service_cls = MagicMock(return_value=mock_service_instance)
    mock_module = MagicMock(IngestionPipelineService=mock_service_cls)
    mock_vec = MagicMock()
    mock_limiter = MagicMock()

    with patch.dict("sys.modules", {"app.services.pipeline": mock_module}):
        ctx: dict[str, object] = {"vector_store": mock_vec, "rate_limiter": mock_limiter}
        job_id = uuid4()
        doc_id = uuid4()
        await run_ingestion_pipeline(ctx, job_id, doc_id, "https://en.wikipedia.org/wiki/Test")
        mock_service_cls.assert_called_once_with(vector_store=mock_vec, rate_limiter=mock_limiter)


def test_ingestion_pipeline_service_wires_rate_limiter_to_default_extractor() -> None:
    """Test that IngestionPipelineService passes rate_limiter to default Crawl4AIExtractor."""
    mock_limiter = InProcessDomainRateLimiter(max_concurrency=3)
    service = IngestionPipelineService(rate_limiter=mock_limiter)

    from app.services.extractors.web import Crawl4AIExtractor

    assert isinstance(service.extractor, Crawl4AIExtractor)
    assert service.extractor.rate_limiter is mock_limiter
