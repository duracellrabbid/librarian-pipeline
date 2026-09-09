"""End-to-end integration tests verifying complete HTTP API workflows."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from app.api.deps import get_db, get_dispatcher, get_vector_store
from app.core.dispatcher import TaskDispatcher
from app.main import app
from app.models.job import JobStatus
from app.services.repository import update_job_status
from app.services.vector_store.qdrant import QdrantVectorStore
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel


@pytest.fixture
async def integration_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a shared in-memory SQLite database session across async requests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def mock_dispatcher() -> AsyncMock:
    """Mock TaskDispatcher for tracking enqueued tasks."""
    mock = AsyncMock(spec=TaskDispatcher)
    mock.enqueue_ingestion_job = AsyncMock()
    return mock


@pytest.fixture
def mock_vector_store() -> AsyncMock:
    """Mock QdrantVectorStore for tracking vector purges."""
    mock = AsyncMock(spec=QdrantVectorStore)
    mock.delete_by_doc_id = AsyncMock(return_value=12)
    return mock


@pytest.fixture
async def integration_client(
    integration_session: AsyncSession,
    mock_dispatcher: AsyncMock,
    mock_vector_store: AsyncMock,
) -> AsyncGenerator[AsyncClient, None]:
    """Provide an AsyncClient configured for full-lifecycle integration testing."""

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield integration_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_dispatcher] = lambda: mock_dispatcher
    app.dependency_overrides[get_vector_store] = lambda: mock_vector_store

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()


class TestCompleteDocumentLifecycle:
    """End-to-end integration tests for the full document ingestion lifecycle."""

    @pytest.mark.asyncio
    async def test_full_document_lifecycle(
        self,
        integration_client: AsyncClient,
        integration_session: AsyncSession,
        mock_dispatcher: AsyncMock,
        mock_vector_store: AsyncMock,
    ) -> None:
        target_url = "https://en.wikipedia.org/wiki/Retrieval-augmented_generation"

        # 1. Verify existence returns false before ingestion
        check_resp = await integration_client.get("/documents/check", params={"url": target_url})
        assert check_resp.status_code == 200
        check_data = check_resp.json()
        assert check_data["exists"] is False
        assert check_data["doc_id"] is None
        assert check_data["status"] is None

        # 2. Submit document for ingestion
        ingest_resp = await integration_client.post(
            "/documents/ingest",
            json={"url": target_url, "title": "RAG Article"},
        )
        assert ingest_resp.status_code == 202
        ingest_data = ingest_resp.json()
        doc_id = ingest_data["doc_id"]
        job_id = ingest_data["job_id"]
        assert ingest_data["status"] == JobStatus.PENDING.value
        mock_dispatcher.enqueue_ingestion_job.assert_awaited_once()

        # 3. Verify existence now returns true with status PENDING
        check_resp2 = await integration_client.get("/documents/check", params={"url": target_url})
        assert check_resp2.status_code == 200
        check_data2 = check_resp2.json()
        assert check_data2["exists"] is True
        assert check_data2["doc_id"] == doc_id
        assert check_data2["status"] == JobStatus.PENDING.value

        # 4. Attempt duplicate ingestion submission -> expects 409 Conflict
        dup_resp = await integration_client.post(
            "/documents/ingest",
            json={"url": target_url, "title": "RAG Duplicate"},
        )
        assert dup_resp.status_code == 409
        assert "already" in dup_resp.json()["detail"].lower()

        # 5. Inspect job status
        status_resp = await integration_client.get(f"/documents/status/{job_id}")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["job_id"] == job_id
        assert status_data["status"] == JobStatus.PENDING.value
        assert status_data["progress_percentage"] == 0

        # Simulate background worker updating job status to INDEXED
        from uuid import UUID

        await update_job_status(
            integration_session,
            job_id=UUID(job_id),
            status=JobStatus.INDEXED,
            progress_percentage=100,
        )

        # Inspect updated job status
        status_resp2 = await integration_client.get(f"/documents/status/{job_id}")
        assert status_resp2.status_code == 200
        assert status_resp2.json()["status"] == JobStatus.INDEXED.value
        assert status_resp2.json()["progress_percentage"] == 100

        # 6. Soft-delete document and purge vectors
        del_resp = await integration_client.delete(f"/documents/{doc_id}")
        assert del_resp.status_code == 200
        del_data = del_resp.json()
        assert del_data["doc_id"] == doc_id
        assert del_data["status"] == "deleted"
        mock_vector_store.delete_by_doc_id.assert_awaited_once_with(doc_id)

        # 7. Verify existence returns false after soft-deletion
        check_resp3 = await integration_client.get("/documents/check", params={"url": target_url})
        assert check_resp3.status_code == 200
        assert check_resp3.json()["exists"] is False

        # Verify deleting again returns 404
        del_again = await integration_client.delete(f"/documents/{doc_id}")
        assert del_again.status_code == 404

        # 8. Verify re-ingestion is permitted after soft-deletion
        reingest_resp = await integration_client.post(
            "/documents/ingest",
            json={"url": target_url, "title": "RAG Re-ingested"},
        )
        assert reingest_resp.status_code == 202
        new_doc_id = reingest_resp.json()["doc_id"]
        assert new_doc_id != doc_id

    @pytest.mark.asyncio
    async def test_api_v1_prefixed_lifecycle(
        self,
        integration_client: AsyncClient,
        mock_dispatcher: AsyncMock,
        mock_vector_store: AsyncMock,
    ) -> None:
        url = "https://en.wikipedia.org/wiki/Natural_language_processing"

        # 1. Check
        res = await integration_client.get("/api/v1/documents/check", params={"url": url})
        assert res.status_code == 200
        assert res.json()["exists"] is False

        # 2. Ingest
        res = await integration_client.post(
            "/api/v1/documents/ingest",
            json={"url": url, "title": "NLP"},
        )
        assert res.status_code == 202
        doc_id = res.json()["doc_id"]
        job_id = res.json()["job_id"]

        # 3. Status
        res = await integration_client.get(f"/api/v1/documents/status/{job_id}")
        assert res.status_code == 200
        assert res.json()["status"] == JobStatus.PENDING.value

        # 4. Delete
        res = await integration_client.delete(f"/api/v1/documents/{doc_id}")
        assert res.status_code == 200
        assert res.json()["status"] == "deleted"
