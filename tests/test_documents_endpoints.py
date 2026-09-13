"""Unit tests for document endpoints domain validation and skipping."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from app.api.deps import get_db, get_dispatcher, get_vector_store
from app.core.dispatcher import TaskDispatcher
from app.main import app
from app.services.vector_store.qdrant import QdrantVectorStore
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel


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


class TestDocumentEndpointsDomainSecurity:
    """Unit tests verifying that document endpoints skip disallowed domains."""

    @pytest.mark.asyncio
    async def test_disallowed_domain_url_is_skipped(
        self,
        client: AsyncClient,
        mock_dispatcher: AsyncMock,
    ) -> None:
        """Verify that submitting a URL with an unallowed domain is skipped with reason domain_not_allowed."""
        payload = {
            "documents": [
                {
                    "url": "https://unallowed.com/article/1",
                    "title": "Unallowed Site",
                }
            ]
        }
        response = await client.post("/api/v1/documents/ingest", json=payload)
        assert response.status_code == 202
        data = response.json()
        assert data["total_submitted"] == 1
        assert data["accepted_count"] == 0
        assert data["skipped_count"] == 1

        mock_dispatcher.enqueue_ingestion_job.assert_not_awaited()

        # Query batch status to verify skipped reason details
        batch_id = data["main_job_id"]
        status_resp = await client.get(f"/api/v1/documents/status/{batch_id}")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert len(status_data["skipped"]) == 1
        assert status_data["skipped"][0]["url"] == "https://unallowed.com/article/1"
        assert status_data["skipped"][0]["reason"] == "domain_not_allowed"

    @pytest.mark.asyncio
    async def test_mixed_allowed_and_disallowed_urls(
        self,
        client: AsyncClient,
        mock_dispatcher: AsyncMock,
    ) -> None:
        """Verify that allowed URLs are accepted while disallowed URLs are skipped in the same batch."""
        payload = {
            "documents": [
                {
                    "url": "https://en.wikipedia.org/wiki/Artificial_intelligence",
                    "title": "Wikipedia AI",
                },
                {
                    "url": "https://evil.attacker.com/payload",
                    "title": "Attacker Domain",
                },
            ]
        }
        response = await client.post("/api/v1/documents/ingest", json=payload)
        assert response.status_code == 202
        data = response.json()
        assert data["total_submitted"] == 2
        assert data["accepted_count"] == 1
        assert data["skipped_count"] == 1

        mock_dispatcher.enqueue_ingestion_job.assert_awaited_once()

        batch_id = data["main_job_id"]
        status_resp = await client.get(f"/api/v1/documents/status/{batch_id}")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert len(status_data["skipped"]) == 1
        assert status_data["skipped"][0]["url"] == "https://evil.attacker.com/payload"
        assert status_data["skipped"][0]["reason"] == "domain_not_allowed"
