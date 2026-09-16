"""Integration unit tests for docset REST API endpoints."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from app.api.deps import get_db, get_dispatcher, get_vector_store
from app.core.config import Settings, get_settings
from app.core.dispatcher import TaskDispatcher
from app.main import app
from app.models import Docset, Document, IngestionJob, JobStatus
from app.services.vector_store.qdrant import QdrantVectorStore
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select


@pytest.fixture
async def async_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated in-memory SQLite database session."""
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
    mock.delete_by_doc_id = AsyncMock(return_value=1)
    mock.delete_by_docset = AsyncMock(return_value=1)
    return mock


@pytest.fixture
def test_settings() -> Settings:
    """Custom settings with small batch limit and allowed domains."""
    return Settings(
        max_batch_ingest_size=5,
        allowed_domains=["https://en.wikipedia.org"],
    )


@pytest.fixture
async def client(
    async_session: AsyncSession,
    mock_dispatcher: AsyncMock,
    mock_vector_store: AsyncMock,
    test_settings: Settings,
) -> AsyncGenerator[AsyncClient, None]:
    """Provide an AsyncClient configured with overridden dependencies."""

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield async_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_dispatcher] = lambda: mock_dispatcher
    app.dependency_overrides[get_vector_store] = lambda: mock_vector_store
    app.dependency_overrides[get_settings] = lambda: test_settings

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client

    app.dependency_overrides.clear()


class TestDocsetIngestEndpoint:
    """Tests for POST /api/v1/docsets/{docset}/documents."""

    @pytest.mark.asyncio
    async def test_successful_batch_ingestion_creates_docset(
        self,
        client: AsyncClient,
        mock_dispatcher: AsyncMock,
        async_session: AsyncSession,
    ) -> None:
        payload = {
            "documents": [
                {"url": "https://en.wikipedia.org/wiki/Python", "title": "Python"},
                {"url": "https://en.wikipedia.org/wiki/Rust", "title": "Rust"},
            ]
        }
        res = await client.post("/api/v1/docsets/coding-docs/documents", json=payload)
        assert res.status_code == 202
        data = res.json()
        assert data["total_submitted"] == 2
        assert data["accepted_count"] == 2
        assert data["skipped_count"] == 0
        assert mock_dispatcher.enqueue_ingestion_job.await_count == 2

        # Verify Docset was created
        ds_res = await async_session.execute(select(Docset).where(Docset.name == "coding-docs"))
        ds = ds_res.scalar_one()
        assert ds.name == "coding-docs"
        assert ds.document_count == 2

    @pytest.mark.asyncio
    async def test_ingest_into_default_docset_rejected(
        self,
        client: AsyncClient,
    ) -> None:
        payload = {"documents": [{"url": "https://en.wikipedia.org/wiki/Test"}]}
        for name in ["default", "DEFAULT", "Default", " default "]:
            res = await client.post(f"/api/v1/docsets/{name}/documents", json=payload)
            assert res.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_ingest_invalid_docset_format_rejected(
        self,
        client: AsyncClient,
    ) -> None:
        payload = {"documents": [{"url": "https://en.wikipedia.org/wiki/Test"}]}
        for bad in ["bad docset", "a" * 65, "bad!name", "UPPER@CASE"]:
            res = await client.post(f"/api/v1/docsets/{bad}/documents", json=payload)
            assert res.status_code == 422

    @pytest.mark.asyncio
    async def test_ingest_batch_size_limit_exceeded(
        self,
        client: AsyncClient,
    ) -> None:
        payload = {"documents": [{"url": f"https://en.wikipedia.org/wiki/Page_{i}"} for i in range(6)]}
        res = await client.post("/api/v1/docsets/test-kb/documents", json=payload)
        assert res.status_code == 422

    @pytest.mark.asyncio
    async def test_ingest_skips_disallowed_domain(
        self,
        client: AsyncClient,
    ) -> None:
        payload = {
            "documents": [
                {"url": "https://disallowed.com/page", "title": "Disallowed"},
                {"url": "https://en.wikipedia.org/wiki/Allowed", "title": "Allowed"},
            ]
        }
        res = await client.post("/api/v1/docsets/mixed-kb/documents", json=payload)
        assert res.status_code == 202
        data = res.json()
        assert data["accepted_count"] == 1
        assert data["skipped_count"] == 1

    @pytest.mark.asyncio
    async def test_same_url_accepted_in_different_docsets(
        self,
        client: AsyncClient,
    ) -> None:
        payload = {"documents": [{"url": "https://en.wikipedia.org/wiki/Shared"}]}
        res1 = await client.post("/api/v1/docsets/docset-one/documents", json=payload)
        assert res1.status_code == 202
        assert res1.json()["accepted_count"] == 1

        res2 = await client.post("/api/v1/docsets/docset-two/documents", json=payload)
        assert res2.status_code == 202
        assert res2.json()["accepted_count"] == 1


class TestDocsetListAndDeletionEndpoints:
    """Tests for GET /api/v1/docsets and DELETE /api/v1/docsets/{docset}."""

    @pytest.mark.asyncio
    async def test_list_docsets_filtering_and_pagination(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
    ) -> None:
        now = datetime.now(UTC)
        ds1 = Docset(name="alpha-docs", document_count=5, created_at=now, updated_at=now)
        ds2 = Docset(name="beta-docs", document_count=2, created_at=now, updated_at=now)
        ds_empty = Docset(name="empty-docs", document_count=0, created_at=now, updated_at=now)
        ds_pruned = Docset(name="pruned-docs", document_count=3, deleted_at=now, created_at=now, updated_at=now)
        async_session.add(ds1)
        async_session.add(ds2)
        async_session.add(ds_empty)
        async_session.add(ds_pruned)
        await async_session.commit()

        res = await client.get("/api/v1/docsets")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 2
        names = [item["name"] for item in data["items"]]
        assert names == ["alpha-docs", "beta-docs"]

        # Pagination
        paged = await client.get("/api/v1/docsets", params={"limit": 1, "offset": 1})
        assert paged.status_code == 200
        pdata = paged.json()
        assert len(pdata["items"]) == 1
        assert pdata["items"][0]["name"] == "beta-docs"

    @pytest.mark.asyncio
    async def test_delete_docset_success(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        mock_vector_store: AsyncMock,
    ) -> None:
        payload = {"documents": [{"url": "https://en.wikipedia.org/wiki/Del_Test"}]}
        await client.post("/api/v1/docsets/to-delete/documents", json=payload)

        res = await client.delete("/api/v1/docsets/to-delete")
        assert res.status_code == 200
        data = res.json()
        assert data["docset"] == "to-delete"
        assert data["status"] == "deleted"
        assert data["deleted_document_count"] == 1
        mock_vector_store.delete_by_docset.assert_awaited_once_with("to-delete")

    @pytest.mark.asyncio
    async def test_delete_docset_not_found(
        self,
        client: AsyncClient,
    ) -> None:
        res = await client.delete("/api/v1/docsets/nonexistent-kb")
        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_default_docset_rejected(
        self,
        client: AsyncClient,
    ) -> None:
        res = await client.delete("/api/v1/docsets/default")
        assert res.status_code in (400, 422)


class TestDocsetScopedDocumentEndpoints:
    """Tests for document listing, check, and deletion scoped to docset."""

    @pytest.mark.asyncio
    async def test_get_docset_indexed_documents(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
    ) -> None:
        now = datetime.now(UTC)
        ds = Docset(name="wiki-kb", document_count=2, created_at=now, updated_at=now)
        async_session.add(ds)
        await async_session.flush()

        doc1 = Document(
            source_type="url",
            source_url="https://en.wikipedia.org/wiki/Quantum",
            title="Quantum Physics",
            docset="wiki-kb",
            created_at=now,
            updated_at=now,
        )
        doc2 = Document(
            source_type="url",
            source_url="https://en.wikipedia.org/wiki/Relativity",
            title="General Relativity",
            docset="wiki-kb",
            created_at=now,
            updated_at=now,
        )
        doc_other = Document(
            source_type="url",
            source_url="https://en.wikipedia.org/wiki/Other",
            title="Other doc",
            docset="other-kb",
            created_at=now,
            updated_at=now,
        )
        async_session.add_all([doc1, doc2, doc_other])
        await async_session.flush()

        job1 = IngestionJob(document_id=doc1.id, status=JobStatus.INDEXED.value, progress_percentage=100)
        job2 = IngestionJob(document_id=doc2.id, status=JobStatus.INDEXED.value, progress_percentage=100)
        job_other = IngestionJob(document_id=doc_other.id, status=JobStatus.INDEXED.value, progress_percentage=100)
        async_session.add_all([job1, job2, job_other])
        await async_session.commit()

        res = await client.get("/api/v1/docsets/wiki-kb/documents")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 2
        urls = [item["source_url"] for item in data["items"]]
        assert "https://en.wikipedia.org/wiki/Quantum" in urls
        assert "https://en.wikipedia.org/wiki/Relativity" in urls
        assert "https://en.wikipedia.org/wiki/Other" not in urls

        # Search query filter
        q_res = await client.get("/api/v1/docsets/wiki-kb/documents", params={"query": "quantum"})
        assert q_res.status_code == 200
        assert q_res.json()["total"] == 1

    @pytest.mark.asyncio
    async def test_check_docset_document_url(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
    ) -> None:
        now = datetime.now(UTC)
        ds = Docset(name="check-kb", document_count=1, created_at=now, updated_at=now)
        doc = Document(
            source_type="url",
            source_url="https://en.wikipedia.org/wiki/Check_Target",
            docset="check-kb",
            created_at=now,
            updated_at=now,
        )
        async_session.add(ds)
        async_session.add(doc)
        await async_session.flush()
        job = IngestionJob(document_id=doc.id, status=JobStatus.INDEXED.value, progress_percentage=100)
        async_session.add(job)
        await async_session.commit()

        # Present in check-kb
        res = await client.get(
            "/api/v1/docsets/check-kb/documents/check",
            params={"url": "https://en.wikipedia.org/wiki/Check_Target"},
        )
        assert res.status_code == 200
        assert res.json()["exists"] is True
        assert res.json()["doc_id"] == str(doc.id)
        assert res.json()["status"] == JobStatus.INDEXED.value

        # Absent in other-kb
        res2 = await client.get(
            "/api/v1/docsets/other-kb/documents/check",
            params={"url": "https://en.wikipedia.org/wiki/Check_Target"},
        )
        assert res2.status_code == 200
        assert res2.json()["exists"] is False
        assert res2.json()["doc_id"] is None

    @pytest.mark.asyncio
    async def test_delete_docset_single_document_and_auto_prunes(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        mock_vector_store: AsyncMock,
    ) -> None:
        payload = {"documents": [{"url": "https://en.wikipedia.org/wiki/Sole_Doc"}]}
        post_res = await client.post("/api/v1/docsets/prune-kb/documents", json=payload)
        assert post_res.status_code == 202

        # Retrieve doc ID
        doc_res = await async_session.execute(
            select(Document).where(Document.source_url == "https://en.wikipedia.org/wiki/Sole_Doc")
        )
        doc = doc_res.scalar_one()

        # Delete single document
        del_res = await client.delete(f"/api/v1/docsets/prune-kb/documents/{doc.id}")
        assert del_res.status_code == 200
        assert del_res.json()["status"] == "deleted"
        mock_vector_store.delete_by_doc_id.assert_awaited_once_with(str(doc.id))

        # Check docset was auto-pruned
        ds_res = await async_session.execute(select(Docset).where(Docset.name == "prune-kb"))
        ds = ds_res.scalar_one()
        assert ds.document_count == 0
        assert ds.deleted_at is not None

        # Deleting again returns 404
        del_again = await client.delete(f"/api/v1/docsets/prune-kb/documents/{doc.id}")
        assert del_again.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_document_in_docset_returns_404(
        self,
        client: AsyncClient,
    ) -> None:
        from uuid import uuid4

        res = await client.delete(f"/api/v1/docsets/any-kb/documents/{uuid4()}")
        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_ingest_all_items_skipped_does_not_enqueue_jobs(
        self,
        client: AsyncClient,
        mock_dispatcher: AsyncMock,
    ) -> None:
        payload = {
            "documents": [
                {"url": "https://disallowed-domain-1.com/page1"},
                {"url": "https://disallowed-domain-2.com/page2"},
            ]
        }
        res = await client.post("/api/v1/docsets/skipped-kb/documents", json=payload)
        assert res.status_code == 202
        data = res.json()
        assert data["total_submitted"] == 2
        assert data["accepted_count"] == 0
        assert data["skipped_count"] == 2
        mock_dispatcher.enqueue_ingestion_job.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_check_docset_document_url_without_jobs(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
    ) -> None:
        now = datetime.now(UTC)
        ds = Docset(name="nojob-kb", document_count=1, created_at=now, updated_at=now)
        doc = Document(
            source_type="url",
            source_url="https://en.wikipedia.org/wiki/No_Job",
            docset="nojob-kb",
            created_at=now,
            updated_at=now,
        )
        async_session.add(ds)
        async_session.add(doc)
        await async_session.commit()

        res = await client.get(
            "/api/v1/docsets/nojob-kb/documents/check",
            params={"url": "https://en.wikipedia.org/wiki/No_Job"},
        )
        assert res.status_code == 200
        assert res.json()["exists"] is True
        assert res.json()["doc_id"] == str(doc.id)
        assert res.json()["status"] is None

    @pytest.mark.asyncio
    async def test_get_docset_indexed_documents_empty(
        self,
        client: AsyncClient,
    ) -> None:
        res = await client.get("/api/v1/docsets/empty-kb/documents")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_list_docsets_empty_db(
        self,
        client: AsyncClient,
    ) -> None:
        res = await client.get("/api/v1/docsets")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 0
        assert data["items"] == []


class TestDocsetDirectEndpointInvocations:
    """Direct invocation unit tests for docset endpoint helper functions."""

    def test_clean_docset_param_valid(self) -> None:
        from app.api.v1.endpoints.docsets import _clean_docset_param

        assert _clean_docset_param("My-Docset_1") == "my-docset_1"
        assert _clean_docset_param("default", allow_reserved=True) == "default"

    def test_clean_docset_param_invalid(self) -> None:
        from app.api.v1.endpoints.docsets import _clean_docset_param
        from app.services.repository import InvalidDocsetNameError, ReservedDocsetNameError

        with pytest.raises(InvalidDocsetNameError):
            _clean_docset_param("invalid/name")

        with pytest.raises(InvalidDocsetNameError):
            _clean_docset_param("")

        with pytest.raises(ReservedDocsetNameError):
            _clean_docset_param("default", allow_reserved=False)

    @pytest.mark.asyncio
    async def test_get_docsets_direct(self, async_session: AsyncSession) -> None:
        from app.api.v1.endpoints.docsets import get_docsets

        now = datetime.now(UTC)
        ds = Docset(name="direct-ds", document_count=1, created_at=now, updated_at=now)
        async_session.add(ds)
        await async_session.commit()

        res = await get_docsets(session=async_session, limit=10, offset=0)
        assert res.total == 1
        assert len(res.items) == 1
        assert res.items[0].name == "direct-ds"

    @pytest.mark.asyncio
    async def test_remove_docset_direct(
        self,
        async_session: AsyncSession,
        mock_vector_store: AsyncMock,
    ) -> None:
        from app.api.v1.endpoints.docsets import remove_docset

        now = datetime.now(UTC)
        ds = Docset(name="direct-del", document_count=1, created_at=now, updated_at=now)
        doc = Document(
            source_type="url",
            source_url="https://en.wikipedia.org/wiki/Direct_Del",
            docset="direct-del",
            created_at=now,
            updated_at=now,
        )
        async_session.add(ds)
        async_session.add(doc)
        await async_session.commit()

        res = await remove_docset(
            docset="direct-del",
            session=async_session,
            vector_store=mock_vector_store,
        )
        assert res.docset == "direct-del"
        assert res.deleted_document_count == 1
        mock_vector_store.delete_by_docset.assert_awaited_once_with("direct-del")

    @pytest.mark.asyncio
    async def test_ingest_into_docset_direct(
        self,
        async_session: AsyncSession,
        mock_dispatcher: AsyncMock,
        test_settings: Settings,
    ) -> None:
        from app.api.schemas import DocumentIngestItem, IngestRequest
        from app.api.v1.endpoints.docsets import ingest_into_docset
        from fastapi import HTTPException

        # Over limit raises HTTPException 422
        over_limit_payload = IngestRequest(
            documents=[DocumentIngestItem(url=f"https://en.wikipedia.org/wiki/Page{i}") for i in range(10)]
        )
        with pytest.raises(HTTPException) as exc_info:
            await ingest_into_docset(
                docset="direct-ingest",
                payload=over_limit_payload,
                session=async_session,
                dispatcher=mock_dispatcher,
                app_settings=test_settings,
            )
        assert exc_info.value.status_code == 422

        # Valid payload succeeds
        valid_payload = IngestRequest(
            documents=[DocumentIngestItem(url="https://en.wikipedia.org/wiki/Direct_Success")]
        )
        resp = await ingest_into_docset(
            docset="direct-ingest",
            payload=valid_payload,
            session=async_session,
            dispatcher=mock_dispatcher,
            app_settings=test_settings,
        )
        assert resp.accepted_count == 1
        assert resp.total_submitted == 1

    @pytest.mark.asyncio
    async def test_get_docset_indexed_documents_direct(
        self,
        async_session: AsyncSession,
    ) -> None:
        from app.api.v1.endpoints.docsets import get_docset_indexed_documents

        resp = await get_docset_indexed_documents(
            docset="empty-direct",
            session=async_session,
            limit=20,
            offset=0,
            query=None,
        )
        assert resp.total == 0
        assert resp.items == []

    @pytest.mark.asyncio
    async def test_check_docset_document_url_direct(
        self,
        async_session: AsyncSession,
    ) -> None:
        from app.api.v1.endpoints.docsets import check_docset_document_url

        # Not found
        resp = await check_docset_document_url(
            docset="check-direct",
            url="https://en.wikipedia.org/wiki/Not_Found",
            session=async_session,
        )
        assert resp.exists is False
        assert resp.doc_id is None

        # Exists without job
        now = datetime.now(UTC)
        ds = Docset(name="check-direct", document_count=1, created_at=now, updated_at=now)
        doc = Document(
            source_type="url",
            source_url="https://en.wikipedia.org/wiki/Found_Doc",
            docset="check-direct",
            created_at=now,
            updated_at=now,
        )
        async_session.add(ds)
        async_session.add(doc)
        await async_session.commit()

        resp_found_no_job = await check_docset_document_url(
            docset="check-direct",
            url="https://en.wikipedia.org/wiki/Found_Doc",
            session=async_session,
        )
        assert resp_found_no_job.exists is True
        assert resp_found_no_job.doc_id == doc.id
        assert resp_found_no_job.status is None

        # Exists with job
        job = IngestionJob(
            document_id=doc.id,
            status=JobStatus.INDEXED.value,
            progress_percentage=100,
            created_at=now,
        )
        async_session.add(job)
        await async_session.commit()

        resp_found_job = await check_docset_document_url(
            docset="check-direct",
            url="https://en.wikipedia.org/wiki/Found_Doc",
            session=async_session,
        )
        assert resp_found_job.exists is True
        assert resp_found_job.doc_id == doc.id
        assert resp_found_job.status == JobStatus.INDEXED.value

    @pytest.mark.asyncio
    async def test_remove_docset_document_direct(
        self,
        async_session: AsyncSession,
        mock_vector_store: AsyncMock,
    ) -> None:
        from uuid import uuid4

        from app.api.v1.endpoints.docsets import remove_docset_document
        from app.services.repository import DocumentNotFoundError

        now = datetime.now(UTC)
        ds = Docset(name="rem-direct", document_count=1, created_at=now, updated_at=now)
        doc = Document(
            source_type="url",
            source_url="https://en.wikipedia.org/wiki/Rem_Direct",
            docset="rem-direct",
            created_at=now,
            updated_at=now,
        )
        async_session.add(ds)
        async_session.add(doc)
        await async_session.commit()

        # Non-existent doc raises DocumentNotFoundError
        with pytest.raises(DocumentNotFoundError):
            await remove_docset_document(
                docset="rem-direct",
                doc_id=uuid4(),
                session=async_session,
                vector_store=mock_vector_store,
            )

        # Existing doc deletes successfully
        resp = await remove_docset_document(
            docset="rem-direct",
            doc_id=doc.id,
            session=async_session,
            vector_store=mock_vector_store,
        )
        assert resp.doc_id == doc.id
        assert resp.status == "deleted"
