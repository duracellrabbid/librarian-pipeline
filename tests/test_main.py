"""Unit tests for FastAPI app setup, middleware, exception handlers, and lifespan in app/main.py."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from app.core.config import settings
from app.core.exceptions import DispatcherError, PipelineError, VectorStoreError
from app.main import app, create_app, lifespan
from app.services.repository import (
    DocumentNotFoundError,
    DuplicateActiveURLError,
    JobNotFoundError,
)
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def test_client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an AsyncClient for testing app endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


class TestAppConfiguration:
    """Tests verifying FastAPI application structure and configuration."""

    def test_create_app(self) -> None:
        test_app = create_app()
        assert test_app.title == settings.app_name

    @pytest.mark.asyncio
    async def test_health_check(self, test_client: AsyncClient) -> None:
        response = await test_client.get("/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["app"] == settings.app_name

    @pytest.mark.asyncio
    async def test_cors_middleware_headers(self, test_client: AsyncClient) -> None:
        response = await test_client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


class TestLifespan:
    """Tests verifying startup and shutdown lifecycle hooks."""

    @pytest.mark.asyncio
    async def test_lifespan_initializes_and_cleans_resources(self) -> None:
        test_app = create_app()

        mock_dispatcher = AsyncMock()
        mock_dispatcher.close = AsyncMock()
        mock_vector_store = AsyncMock()
        mock_vector_store.close = AsyncMock()
        mock_engine = AsyncMock()
        mock_engine.dispose = AsyncMock()

        with (
            patch("app.main.ArqTaskDispatcher", return_value=mock_dispatcher),
            patch("app.main.QdrantVectorStore", return_value=mock_vector_store),
            patch("app.main.engine", mock_engine),
        ):
            async with lifespan(test_app):
                assert test_app.state.dispatcher is mock_dispatcher
                assert test_app.state.vector_store is mock_vector_store

            mock_vector_store.initialize_collection.assert_awaited_once()
            mock_dispatcher.close.assert_awaited_once()
            mock_vector_store.close.assert_awaited_once()
            mock_engine.dispose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lifespan_vector_store_initialization_failure_logged(self) -> None:
        test_app = create_app()

        mock_dispatcher = AsyncMock()
        mock_dispatcher.close = AsyncMock()
        mock_vector_store = AsyncMock()
        mock_vector_store.initialize_collection.side_effect = Exception("Connection refused")
        mock_vector_store.close = AsyncMock()
        mock_engine = AsyncMock()
        mock_engine.dispose = AsyncMock()

        with (
            patch("app.main.ArqTaskDispatcher", return_value=mock_dispatcher),
            patch("app.main.QdrantVectorStore", return_value=mock_vector_store),
            patch("app.main.engine", mock_engine),
        ):
            async with lifespan(test_app):
                assert test_app.state.vector_store is mock_vector_store

            mock_vector_store.initialize_collection.assert_awaited_once()
            mock_vector_store.close.assert_awaited_once()


class TestExceptionHandlers:
    """Tests verifying domain and repository exception handlers."""

    @pytest.mark.asyncio
    async def test_duplicate_active_url_handler(self) -> None:
        test_app = create_app()

        @test_app.get("/test-duplicate")
        async def raise_duplicate():
            raise DuplicateActiveURLError("URL already ingested")

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/test-duplicate")
            assert resp.status_code == 409
            assert resp.json()["detail"] == "URL already ingested"

    @pytest.mark.asyncio
    async def test_job_not_found_handler(self) -> None:
        test_app = create_app()

        @test_app.get("/test-job-not-found")
        async def raise_job_not_found():
            raise JobNotFoundError("Job not found")

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/test-job-not-found")
            assert resp.status_code == 404
            assert resp.json()["detail"] == "Job not found"

    @pytest.mark.asyncio
    async def test_document_not_found_handler(self) -> None:
        test_app = create_app()

        @test_app.get("/test-doc-not-found")
        async def raise_doc_not_found():
            raise DocumentNotFoundError("Document not found")

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/test-doc-not-found")
            assert resp.status_code == 404
            assert resp.json()["detail"] == "Document not found"

    @pytest.mark.asyncio
    async def test_vector_store_error_handler(self) -> None:
        test_app = create_app()

        @test_app.get("/test-vector-error")
        async def raise_vector_error():
            raise VectorStoreError("Vector store unavailable")

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/test-vector-error")
            assert resp.status_code == 502
            assert resp.json()["detail"] == "Vector store unavailable"

    @pytest.mark.asyncio
    async def test_dispatcher_error_handler(self) -> None:
        test_app = create_app()

        @test_app.get("/test-dispatcher-error")
        async def raise_dispatcher_error():
            raise DispatcherError("Failed to enqueue job")

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/test-dispatcher-error")
            assert resp.status_code == 500
            assert resp.json()["detail"] == "Failed to enqueue job"

    @pytest.mark.asyncio
    async def test_pipeline_error_handler(self) -> None:
        test_app = create_app()

        @test_app.get("/test-pipeline-error")
        async def raise_pipeline_error():
            raise PipelineError("Unexpected pipeline failure")

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/test-pipeline-error")
            assert resp.status_code == 500
            assert resp.json()["detail"] == "Unexpected pipeline failure"
