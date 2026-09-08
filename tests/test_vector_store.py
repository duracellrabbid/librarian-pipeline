"""Unit tests for Qdrant vector store adapter and exceptions."""

import pytest
from app.core.exceptions import PipelineError, VectorStoreError


def test_vector_store_error_attributes_and_hierarchy() -> None:
    """Test VectorStoreError attributes, collection_name, status_code, and inheritance."""
    err = VectorStoreError(
        "Failed to connect to Qdrant",
        collection_name="knowledge_base",
        status_code=503,
    )
    assert isinstance(err, PipelineError)
    assert isinstance(err, Exception)
    assert str(err) == "Failed to connect to Qdrant"
    assert err.collection_name == "knowledge_base"
    assert err.status_code == 503


def test_vector_store_error_defaults() -> None:
    """Test VectorStoreError default optional attributes."""
    err = VectorStoreError("Generic vector store failure")
    assert str(err) == "Generic vector store failure"
    assert err.collection_name is None
    assert err.status_code is None


def test_vector_search_result_model() -> None:
    """Test VectorSearchResult pydantic model serialization and fields."""
    from app.services.vector_store.base import VectorSearchResult

    res = VectorSearchResult(
        point_id="123e4567-e89b-12d3-a456-426614174000",
        score=0.92,
        payload={"doc_id": "doc_1", "text": "Sample chunk text"},
    )
    assert res.point_id == "123e4567-e89b-12d3-a456-426614174000"
    assert res.score == 0.92
    assert res.payload["doc_id"] == "doc_1"


def test_base_vector_store_protocol_conformance() -> None:
    """Test BaseVectorStore protocol compliance with runtime checkable behavior."""
    from app.services.chunkers.base import DocumentChunk
    from app.services.vector_store.base import BaseVectorStore, VectorSearchResult

    class ValidStore:
        async def initialize_collection(self) -> None:
            pass

        async def upsert_chunks(
            self,
            doc_id: str,
            chunks: list[DocumentChunk],
            vectors: list[list[float]],
            source_url: str | None = None,
        ) -> int:
            return len(chunks)

        async def delete_by_doc_id(self, doc_id: str) -> int:
            return 1

        async def search(
            self,
            query_vector: list[float],
            limit: int = 5,
            doc_id: str | None = None,
            score_threshold: float | None = None,
        ) -> list[VectorSearchResult]:
            return []

    class IncompleteStore:
        async def initialize_collection(self) -> None:
            pass

    assert isinstance(ValidStore(), BaseVectorStore)
    assert not isinstance(IncompleteStore(), BaseVectorStore)


@pytest.mark.asyncio
async def test_qdrant_store_protocol_conformance() -> None:
    """Test QdrantVectorStore conforms to BaseVectorStore protocol."""
    from unittest.mock import AsyncMock

    from app.services.vector_store.base import BaseVectorStore
    from app.services.vector_store.qdrant import QdrantVectorStore
    from qdrant_client import AsyncQdrantClient

    mock_client = AsyncMock(spec=AsyncQdrantClient)
    store = QdrantVectorStore(client=mock_client)
    assert isinstance(store, BaseVectorStore)


def test_qdrant_store_init_defaults() -> None:
    """Test QdrantVectorStore initialization with default settings."""
    from app.core.config import settings
    from app.services.vector_store.qdrant import QdrantVectorStore

    store = QdrantVectorStore()
    assert store.collection_name == "knowledge_base"
    assert store.dimension == 1024
    assert store.url == settings.qdrant_url
    assert store.api_key == settings.qdrant_api_key


@pytest.mark.asyncio
async def test_qdrant_store_lifecycle_and_custom_init() -> None:
    """Test QdrantVectorStore custom options and context manager lifecycle."""
    from unittest.mock import AsyncMock

    from app.services.vector_store.qdrant import QdrantVectorStore
    from qdrant_client import AsyncQdrantClient

    mock_client = AsyncMock(spec=AsyncQdrantClient)
    async with QdrantVectorStore(
        collection_name="custom_kb",
        dimension=512,
        url="http://custom-qdrant:6333",
        api_key="secret",
        client=mock_client,
    ) as store:
        assert store.collection_name == "custom_kb"
        assert store.dimension == 512
        assert store.url == "http://custom-qdrant:6333"
        assert store.api_key == "secret"
        client = await store.get_client()
        assert client is mock_client

    # Injected client should not be closed by store
    mock_client.close.assert_not_called()


@pytest.mark.asyncio
async def test_qdrant_store_owns_client_close() -> None:
    """Test QdrantVectorStore closes internally created client."""
    from app.services.vector_store.qdrant import QdrantVectorStore

    store = QdrantVectorStore()
    client = await store.get_client()
    assert client is not None
    await store.close()


@pytest.mark.asyncio
async def test_initialize_collection_when_not_exists() -> None:
    """Test initialize_collection creates collection and payload index when missing."""
    from unittest.mock import AsyncMock, MagicMock

    from app.services.vector_store.qdrant import QdrantVectorStore
    from qdrant_client import AsyncQdrantClient, models

    mock_client = AsyncMock(spec=AsyncQdrantClient)
    mock_client.collection_exists.return_value = False
    mock_info = MagicMock()
    mock_info.payload_schema = {}
    mock_client.get_collection.return_value = mock_info

    store = QdrantVectorStore(client=mock_client)
    await store.initialize_collection()

    mock_client.create_collection.assert_awaited_once_with(
        collection_name="knowledge_base",
        vectors_config=models.VectorParams(
            size=1024,
            distance=models.Distance.COSINE,
        ),
    )
    mock_client.create_payload_index.assert_awaited_once_with(
        collection_name="knowledge_base",
        field_name="doc_id",
        field_schema=models.PayloadSchemaType.KEYWORD,
    )


@pytest.mark.asyncio
async def test_initialize_collection_when_already_exists() -> None:
    """Test initialize_collection is idempotent when collection and index already exist."""
    from unittest.mock import AsyncMock, MagicMock

    from app.services.vector_store.qdrant import QdrantVectorStore
    from qdrant_client import AsyncQdrantClient

    mock_client = AsyncMock(spec=AsyncQdrantClient)
    mock_client.collection_exists.return_value = True
    mock_info = MagicMock()
    mock_info.payload_schema = {"doc_id": MagicMock()}
    mock_client.get_collection.return_value = mock_info

    store = QdrantVectorStore(client=mock_client)
    await store.initialize_collection()

    mock_client.create_collection.assert_not_called()
    mock_client.create_payload_index.assert_not_called()


@pytest.mark.asyncio
async def test_initialize_collection_error_raises_vector_store_error() -> None:
    """Test initialize_collection failure wraps exception in VectorStoreError."""
    from unittest.mock import AsyncMock

    from app.core.exceptions import VectorStoreError
    from app.services.vector_store.qdrant import QdrantVectorStore
    from qdrant_client import AsyncQdrantClient

    mock_client = AsyncMock(spec=AsyncQdrantClient)
    mock_client.collection_exists.side_effect = RuntimeError("Qdrant connection refused")

    store = QdrantVectorStore(client=mock_client)
    with pytest.raises(VectorStoreError) as exc_info:
        await store.initialize_collection()

    assert "Failed to initialize Qdrant collection" in str(exc_info.value)
    assert exc_info.value.collection_name == "knowledge_base"


@pytest.mark.asyncio
async def test_upsert_chunks_success() -> None:
    """Test successful upsert with deterministic UUIDs and comprehensive payload."""
    import uuid
    from unittest.mock import AsyncMock

    from app.services.chunkers.base import DocumentChunk
    from app.services.vector_store.qdrant import QdrantVectorStore
    from qdrant_client import AsyncQdrantClient

    mock_client = AsyncMock(spec=AsyncQdrantClient)
    store = QdrantVectorStore(client=mock_client)

    chunks = [
        DocumentChunk(
            chunk_index=0,
            text="First section text",
            metadata={"heading_path": ["Introduction", "Overview"], "custom_tag": "test_tag"},
        ),
        DocumentChunk(
            chunk_index=1,
            text="Second section text",
            metadata={"heading_path": ["Introduction", "Details"]},
        ),
    ]
    vectors = [[0.1] * 1024, [0.2] * 1024]

    count = await store.upsert_chunks(
        doc_id="doc-abc",
        chunks=chunks,
        vectors=vectors,
        source_url="https://docs.example.com/page",
    )
    assert count == 2

    mock_client.upsert.assert_awaited_once()
    call_kwargs = mock_client.upsert.call_args.kwargs
    assert call_kwargs["collection_name"] == "knowledge_base"
    assert call_kwargs["wait"] is True

    points = call_kwargs["points"]
    assert len(points) == 2

    expected_id_0 = str(uuid.uuid5(uuid.NAMESPACE_DNS, "doc-abc:0"))
    assert points[0].id == expected_id_0
    assert points[0].vector == vectors[0]
    assert points[0].payload["doc_id"] == "doc-abc"
    assert points[0].payload["chunk_index"] == 0
    assert points[0].payload["text"] == "First section text"
    assert points[0].payload["source_url"] == "https://docs.example.com/page"
    assert points[0].payload["heading_path"] == ["Introduction", "Overview"]
    assert points[0].payload["custom_tag"] == "test_tag"

    expected_id_1 = str(uuid.uuid5(uuid.NAMESPACE_DNS, "doc-abc:1"))
    assert points[1].id == expected_id_1


@pytest.mark.asyncio
async def test_upsert_chunks_empty_list() -> None:
    """Test upsert_chunks with empty chunks returns 0 without calling client."""
    from unittest.mock import AsyncMock

    from app.services.vector_store.qdrant import QdrantVectorStore
    from qdrant_client import AsyncQdrantClient

    mock_client = AsyncMock(spec=AsyncQdrantClient)
    store = QdrantVectorStore(client=mock_client)

    count = await store.upsert_chunks(doc_id="doc-123", chunks=[], vectors=[])
    assert count == 0
    mock_client.upsert.assert_not_called()


@pytest.mark.asyncio
async def test_upsert_chunks_empty_doc_id_raises() -> None:
    """Test upsert_chunks with empty doc_id raises VectorStoreError."""
    from app.core.exceptions import VectorStoreError
    from app.services.chunkers.base import DocumentChunk
    from app.services.vector_store.qdrant import QdrantVectorStore

    store = QdrantVectorStore()
    chunk = DocumentChunk(chunk_index=0, text="text")
    with pytest.raises(VectorStoreError, match="doc_id cannot be empty"):
        await store.upsert_chunks(doc_id="   ", chunks=[chunk], vectors=[[0.1] * 1024])


@pytest.mark.asyncio
async def test_upsert_chunks_length_mismatch_raises() -> None:
    """Test upsert_chunks with mismatched chunks and vectors count raises VectorStoreError."""
    from app.core.exceptions import VectorStoreError
    from app.services.chunkers.base import DocumentChunk
    from app.services.vector_store.qdrant import QdrantVectorStore

    store = QdrantVectorStore()
    chunk = DocumentChunk(chunk_index=0, text="text")
    with pytest.raises(VectorStoreError, match="Chunks count .* does not match vectors count"):
        await store.upsert_chunks(doc_id="doc-1", chunks=[chunk], vectors=[])


@pytest.mark.asyncio
async def test_upsert_chunks_dimension_mismatch_raises() -> None:
    """Test upsert_chunks with invalid vector dimension raises VectorStoreError."""
    from app.core.exceptions import VectorStoreError
    from app.services.chunkers.base import DocumentChunk
    from app.services.vector_store.qdrant import QdrantVectorStore

    store = QdrantVectorStore(dimension=1024)
    chunk = DocumentChunk(chunk_index=0, text="text")
    with pytest.raises(VectorStoreError, match="Vector dimension mismatch"):
        await store.upsert_chunks(doc_id="doc-1", chunks=[chunk], vectors=[[0.1] * 512])


@pytest.mark.asyncio
async def test_upsert_chunks_client_error_raises_vector_store_error() -> None:
    """Test upsert_chunks wraps Qdrant client errors in VectorStoreError."""
    from unittest.mock import AsyncMock

    from app.core.exceptions import VectorStoreError
    from app.services.chunkers.base import DocumentChunk
    from app.services.vector_store.qdrant import QdrantVectorStore
    from qdrant_client import AsyncQdrantClient

    mock_client = AsyncMock(spec=AsyncQdrantClient)
    mock_client.upsert.side_effect = RuntimeError("Upsert failed: timeout")
    store = QdrantVectorStore(client=mock_client)

    chunk = DocumentChunk(chunk_index=0, text="text")
    with pytest.raises(VectorStoreError, match="Failed to upsert chunks"):
        await store.upsert_chunks(doc_id="doc-1", chunks=[chunk], vectors=[[0.1] * 1024])


@pytest.mark.asyncio
async def test_delete_by_doc_id_success() -> None:
    """Test delete_by_doc_id builds filter and calls client.delete."""
    from unittest.mock import AsyncMock

    from app.services.vector_store.qdrant import QdrantVectorStore
    from qdrant_client import AsyncQdrantClient, models

    mock_client = AsyncMock(spec=AsyncQdrantClient)
    mock_result = AsyncMock()
    mock_client.delete.return_value = mock_result
    store = QdrantVectorStore(client=mock_client)

    result = await store.delete_by_doc_id("doc-xyz")
    assert result >= 0

    mock_client.delete.assert_awaited_once()
    call_kwargs = mock_client.delete.call_args.kwargs
    assert call_kwargs["collection_name"] == "knowledge_base"
    assert call_kwargs["wait"] is True

    selector = call_kwargs["points_selector"]
    assert isinstance(selector, models.Filter)
    assert len(selector.must) == 1
    condition = selector.must[0]
    assert condition.key == "doc_id"
    assert condition.match.value == "doc-xyz"


@pytest.mark.asyncio
async def test_delete_by_doc_id_empty_raises() -> None:
    """Test delete_by_doc_id with empty doc_id raises VectorStoreError."""
    from app.core.exceptions import VectorStoreError
    from app.services.vector_store.qdrant import QdrantVectorStore

    store = QdrantVectorStore()
    with pytest.raises(VectorStoreError, match="doc_id cannot be empty"):
        await store.delete_by_doc_id("   ")


@pytest.mark.asyncio
async def test_delete_by_doc_id_client_error_raises_vector_store_error() -> None:
    """Test delete_by_doc_id wraps client error in VectorStoreError."""
    from unittest.mock import AsyncMock

    from app.core.exceptions import VectorStoreError
    from app.services.vector_store.qdrant import QdrantVectorStore
    from qdrant_client import AsyncQdrantClient

    mock_client = AsyncMock(spec=AsyncQdrantClient)
    mock_client.delete.side_effect = RuntimeError("Delete error")
    store = QdrantVectorStore(client=mock_client)

    with pytest.raises(VectorStoreError, match="Failed to delete points for doc_id 'doc-err'"):
        await store.delete_by_doc_id("doc-err")


@pytest.mark.asyncio
async def test_search_success() -> None:
    """Test search calls query_points and parses results into VectorSearchResult."""
    from unittest.mock import AsyncMock, MagicMock

    from app.services.vector_store.base import VectorSearchResult
    from app.services.vector_store.qdrant import QdrantVectorStore
    from qdrant_client import AsyncQdrantClient

    mock_client = AsyncMock(spec=AsyncQdrantClient)

    point_1 = MagicMock()
    point_1.id = "uuid-1"
    point_1.score = 0.95
    point_1.payload = {"doc_id": "doc-1", "text": "First match"}

    point_2 = MagicMock()
    point_2.id = "uuid-2"
    point_2.score = 0.88
    point_2.payload = {"doc_id": "doc-2", "text": "Second match"}

    mock_response = MagicMock()
    mock_response.points = [point_1, point_2]
    mock_client.query_points.return_value = mock_response

    store = QdrantVectorStore(client=mock_client)
    query_vector = [0.05] * 1024
    results = await store.search(
        query_vector=query_vector,
        limit=2,
        score_threshold=0.8,
    )

    assert len(results) == 2
    assert isinstance(results[0], VectorSearchResult)
    assert results[0].point_id == "uuid-1"
    assert results[0].score == 0.95
    assert results[0].payload["text"] == "First match"
    assert results[1].point_id == "uuid-2"

    mock_client.query_points.assert_awaited_once()
    call_kwargs = mock_client.query_points.call_args.kwargs
    assert call_kwargs["collection_name"] == "knowledge_base"
    assert call_kwargs["query"] == query_vector
    assert call_kwargs["limit"] == 2
    assert call_kwargs["score_threshold"] == 0.8
    assert call_kwargs["query_filter"] is None
    assert call_kwargs["with_payload"] is True


@pytest.mark.asyncio
async def test_search_with_doc_id_filter() -> None:
    """Test search applies doc_id filter when provided."""
    from unittest.mock import AsyncMock, MagicMock

    from app.services.vector_store.qdrant import QdrantVectorStore
    from qdrant_client import AsyncQdrantClient, models

    mock_client = AsyncMock(spec=AsyncQdrantClient)
    mock_response = MagicMock()
    mock_response.points = []
    mock_client.query_points.return_value = mock_response

    store = QdrantVectorStore(client=mock_client)
    await store.search(
        query_vector=[0.05] * 1024,
        limit=5,
        doc_id="scoped-doc-123",
    )

    mock_client.query_points.assert_awaited_once()
    call_kwargs = mock_client.query_points.call_args.kwargs
    query_filter = call_kwargs["query_filter"]
    assert isinstance(query_filter, models.Filter)
    assert len(query_filter.must) == 1
    assert query_filter.must[0].key == "doc_id"
    assert query_filter.must[0].match.value == "scoped-doc-123"


@pytest.mark.asyncio
async def test_search_dimension_mismatch_raises() -> None:
    """Test search with mismatched vector dimensions raises VectorStoreError."""
    from app.core.exceptions import VectorStoreError
    from app.services.vector_store.qdrant import QdrantVectorStore

    store = QdrantVectorStore(dimension=1024)
    with pytest.raises(VectorStoreError, match="Query vector dimension mismatch"):
        await store.search(query_vector=[0.1] * 512)


@pytest.mark.asyncio
async def test_search_client_error_raises_vector_store_error() -> None:
    """Test search wraps Qdrant client errors in VectorStoreError."""
    from unittest.mock import AsyncMock

    from app.core.exceptions import VectorStoreError
    from app.services.vector_store.qdrant import QdrantVectorStore
    from qdrant_client import AsyncQdrantClient

    mock_client = AsyncMock(spec=AsyncQdrantClient)
    mock_client.query_points.side_effect = RuntimeError("Search index timeout")
    store = QdrantVectorStore(client=mock_client)

    with pytest.raises(VectorStoreError, match="Vector search failed"):
        await store.search(query_vector=[0.1] * 1024)
