"""Unit tests for REST API document endpoints using httpx.AsyncClient and mocked dependencies."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.api.deps import get_db, get_dispatcher, get_vector_store
from app.core.dispatcher import TaskDispatcher
from app.core.exceptions import DispatcherError, VectorStoreError
from app.main import app
from app.models import Document, JobStatus
from app.services.repository import create_document_and_job
from app.services.vector_store.qdrant import QdrantVectorStore
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select


@pytest.fixture
async def async_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated in-memory SQLite async database session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
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
    """Mock TaskDispatcher dependency."""
    mock = AsyncMock(spec=TaskDispatcher)
    mock.enqueue_ingestion_job = AsyncMock()
    return mock


@pytest.fixture
def mock_vector_store() -> AsyncMock:
    """Mock QdrantVectorStore dependency."""
    mock = AsyncMock(spec=QdrantVectorStore)
    mock.delete_by_doc_id = AsyncMock(return_value=5)
    return mock


@pytest.fixture
async def client(
    async_session: AsyncSession,
    mock_dispatcher: AsyncMock,
    mock_vector_store: AsyncMock,
) -> AsyncGenerator[AsyncClient, None]:
    """Provide an AsyncClient configured with overridden dependencies."""

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield async_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_dispatcher] = lambda: mock_dispatcher
    app.dependency_overrides[get_vector_store] = lambda: mock_vector_store

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client

    app.dependency_overrides.clear()


class TestIngestEndpoint:
    """Tests for POST /documents/ingest endpoint."""

    @pytest.mark.asyncio
    async def test_successful_ingestion_submission(
        self,
        client: AsyncClient,
        mock_dispatcher: AsyncMock,
    ) -> None:
        payload = {
            "url": "https://en.wikipedia.org/wiki/Artificial_intelligence",
            "title": "AI Wiki",
        }
        response = await client.post("/documents/ingest", json=payload)
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == JobStatus.PENDING.value
        assert "job_id" in data
        assert "doc_id" in data
        mock_dispatcher.enqueue_ingestion_job.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_duplicate_active_url_rejection(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
    ) -> None:
        url = "https://en.wikipedia.org/wiki/Duplicate_Test"
        await create_document_and_job(async_session, source_type="url", source_url=url)

        payload = {"url": url}
        response = await client.post("/documents/ingest", json=payload)
        assert response.status_code == 409
        detail = response.json()["detail"].lower()
        assert "already" in detail

    @pytest.mark.asyncio
    async def test_invalid_url_returns_422(self, client: AsyncClient) -> None:
        payload = {"url": "not-a-valid-url"}
        response = await client.post("/documents/ingest", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_dispatcher_failure_returns_500(
        self,
        client: AsyncClient,
        mock_dispatcher: AsyncMock,
    ) -> None:
        mock_dispatcher.enqueue_ingestion_job.side_effect = DispatcherError("Queue failure")
        payload = {"url": "https://en.wikipedia.org/wiki/Failure_Test"}
        response = await client.post("/documents/ingest", json=payload)
        assert response.status_code == 500


class TestStatusEndpoint:
    """Tests for GET /documents/status/{job_id} endpoint."""

    @pytest.mark.asyncio
    async def test_status_existing_job(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
    ) -> None:
        _, job = await create_document_and_job(
            async_session,
            source_type="url",
            source_url="https://example.com/status-test",
        )
        response = await client.get(f"/documents/status/{job.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == str(job.id)
        assert data["status"] == JobStatus.PENDING.value
        assert data["progress_percentage"] == 0

    @pytest.mark.asyncio
    async def test_status_non_existent_job_returns_404(
        self,
        client: AsyncClient,
    ) -> None:
        non_existent_id = uuid4()
        response = await client.get(f"/documents/status/{non_existent_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_status_invalid_uuid_returns_422(
        self,
        client: AsyncClient,
    ) -> None:
        response = await client.get("/documents/status/invalid-uuid")
        assert response.status_code == 422


class TestCheckEndpoint:
    """Tests for GET /documents/check endpoint."""

    @pytest.mark.asyncio
    async def test_check_active_url_exists(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
    ) -> None:
        url = "https://example.com/check-active"
        doc, job = await create_document_and_job(
            async_session,
            source_type="url",
            source_url=url,
        )
        response = await client.get("/documents/check", params={"url": url})
        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is True
        assert data["doc_id"] == str(doc.id)
        assert data["status"] == job.status

    @pytest.mark.asyncio
    async def test_check_non_existent_url(
        self,
        client: AsyncClient,
    ) -> None:
        response = await client.get(
            "/documents/check",
            params={"url": "https://example.com/absent"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is False
        assert data["doc_id"] is None
        assert data["status"] is None

    @pytest.mark.asyncio
    async def test_check_soft_deleted_url_returns_not_exists(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
    ) -> None:
        url = "https://example.com/check-deleted"
        doc, _ = await create_document_and_job(
            async_session,
            source_type="url",
            source_url=url,
        )
        from app.services.repository import soft_delete_document

        await soft_delete_document(async_session, doc.id)

        response = await client.get("/documents/check", params={"url": url})
        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is False
        assert data["doc_id"] is None
        assert data["status"] is None

    @pytest.mark.asyncio
    async def test_check_missing_url_returns_422(
        self,
        client: AsyncClient,
    ) -> None:
        response = await client.get("/documents/check")
        assert response.status_code == 422


class TestDeleteEndpoint:
    """Tests for DELETE /documents/{doc_id} endpoint."""

    @pytest.mark.asyncio
    async def test_successful_document_deletion(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        mock_vector_store: AsyncMock,
    ) -> None:
        doc, _ = await create_document_and_job(
            async_session,
            source_type="url",
            source_url="https://example.com/delete-test",
        )
        response = await client.delete(f"/documents/{doc.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["doc_id"] == str(doc.id)
        assert data["status"] == "deleted"

        mock_vector_store.delete_by_doc_id.assert_awaited_once_with(str(doc.id))

        # Verify DB soft deletion
        stmt = select(Document).where(Document.id == doc.id)
        res = await async_session.execute(stmt)
        refreshed = res.scalars().first()
        assert refreshed is not None
        assert refreshed.deleted_at is not None

    @pytest.mark.asyncio
    async def test_delete_non_existent_document_returns_404(
        self,
        client: AsyncClient,
    ) -> None:
        response = await client.delete(f"/documents/{uuid4()}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_already_soft_deleted_document_returns_404(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
    ) -> None:
        doc, _ = await create_document_and_job(
            async_session,
            source_type="url",
            source_url="https://example.com/already-deleted",
        )
        from app.services.repository import soft_delete_document

        await soft_delete_document(async_session, doc.id)

        response = await client.delete(f"/documents/{doc.id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_vector_store_failure_aborts_db_deletion(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        mock_vector_store: AsyncMock,
    ) -> None:
        mock_vector_store.delete_by_doc_id.side_effect = VectorStoreError("Qdrant error")

        doc, _ = await create_document_and_job(
            async_session,
            source_type="url",
            source_url="https://example.com/abort-test",
        )

        response = await client.delete(f"/documents/{doc.id}")
        assert response.status_code == 502

        # Verify DB record is NOT soft-deleted
        stmt = select(Document).where(Document.id == doc.id)
        res = await async_session.execute(stmt)
        refreshed = res.scalars().first()
        assert refreshed is not None
        assert refreshed.deleted_at is None

    @pytest.mark.asyncio
    async def test_api_v1_prefix_routes(
        self,
        client: AsyncClient,
    ) -> None:
        response = await client.get(
            "/api/v1/documents/check", params={"url": "https://notfound.com"}
        )
        assert response.status_code == 200


class TestDirectHandlerInvocations:
    """Direct invocation unit tests for document endpoint handler functions."""

    @pytest.mark.asyncio
    async def test_direct_ingest_document(
        self,
        async_session: AsyncSession,
        mock_dispatcher: AsyncMock,
    ) -> None:
        from app.api.schemas import IngestRequest
        from app.api.v1.endpoints.documents import ingest_document

        req = IngestRequest(url="https://example.com/direct-ingest", title="Direct Title")
        resp = await ingest_document(req, async_session, mock_dispatcher)
        assert resp.status == JobStatus.PENDING.value
        mock_dispatcher.enqueue_ingestion_job.assert_awaited()

    @pytest.mark.asyncio
    async def test_direct_get_job_status(
        self,
        async_session: AsyncSession,
    ) -> None:
        from app.api.v1.endpoints.documents import get_job_status
        from app.services.repository import JobNotFoundError

        _, job = await create_document_and_job(
            async_session,
            source_type="url",
            source_url="https://example.com/direct-status",
        )
        resp = await get_job_status(job.id, async_session)
        assert resp.job_id == job.id

        with pytest.raises(JobNotFoundError):
            await get_job_status(uuid4(), async_session)

    @pytest.mark.asyncio
    async def test_direct_check_document_url(
        self,
        async_session: AsyncSession,
    ) -> None:
        from app.api.v1.endpoints.documents import check_document_url

        url = "https://example.com/direct-check"
        doc, _ = await create_document_and_job(
            async_session,
            source_type="url",
            source_url=url,
        )
        resp = await check_document_url(url, async_session)
        assert resp.exists is True
        assert resp.doc_id == doc.id

        absent = await check_document_url("https://example.com/direct-absent", async_session)
        assert absent.exists is False

    @pytest.mark.asyncio
    async def test_direct_delete_document(
        self,
        async_session: AsyncSession,
        mock_vector_store: AsyncMock,
    ) -> None:
        from app.api.v1.endpoints.documents import delete_document
        from app.services.repository import DocumentNotFoundError

        doc, _ = await create_document_and_job(
            async_session,
            source_type="url",
            source_url="https://example.com/direct-delete",
        )
        resp = await delete_document(doc.id, async_session, mock_vector_store)
        assert resp.doc_id == doc.id
        assert resp.status == "deleted"

        with pytest.raises(DocumentNotFoundError):
            await delete_document(uuid4(), async_session, mock_vector_store)
