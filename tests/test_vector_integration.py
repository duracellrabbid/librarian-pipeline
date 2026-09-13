"""Integration tests connecting chunking, embeddings, and vector storage."""

import math
import uuid
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from app.core.config import settings
from app.services.chunkers.hybrid import HybridMarkdownChunker
from app.services.embeddings.ollama import OllamaEmbeddingClient
from app.services.vector_store.qdrant import QdrantVectorStore
from qdrant_client import models

SAMPLE_DOCUMENT_MARKDOWN = """# Machine Learning Infrastructure

Machine learning infrastructure powers modern AI workloads and applications.

## Vector Search

Vector databases enable approximate nearest neighbor search across dense embeddings.
They support metadata payload filtering and sub-millisecond retrieval.

### Indexing Strategies

HNSW and IVF are widely used indexing techniques for vector similarity retrieval.
Payload indexing allows filtering by document identifiers before or during vector ranking.

## Embedding Models

Dense representation models like BGE-M3 produce multilingual embeddings.
These models encode semantic meaning into fixed-dimensional vectors such as 1024 dimensions.
"""


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    dot = sum(a * b for a, b in zip(v1, v2, strict=True))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


class SimulatedQdrantClient:
    """Simulated in-memory AsyncQdrantClient for end-to-end vector pipeline testing."""

    def __init__(self) -> None:
        self.collections: dict[str, dict[str, Any]] = {}
        self.points: dict[str, dict[str, models.PointStruct]] = {}
        self.indexes: dict[str, set[str]] = {}

    async def collection_exists(self, collection_name: str) -> bool:
        return collection_name in self.collections

    async def create_collection(
        self,
        collection_name: str,
        vectors_config: models.VectorParams,
    ) -> bool:
        self.collections[collection_name] = {"vectors_config": vectors_config}
        self.points[collection_name] = {}
        self.indexes[collection_name] = set()
        return True

    async def get_collection(self, collection_name: str) -> Any:
        class CollectionInfo:
            def __init__(self, schema: set[str]) -> None:
                self.payload_schema = dict.fromkeys(schema, "keyword")

        return CollectionInfo(self.indexes.get(collection_name, set()))

    async def create_payload_index(
        self,
        collection_name: str,
        field_name: str,
        field_schema: Any,
    ) -> bool:
        self.indexes.setdefault(collection_name, set()).add(field_name)
        return True

    async def upsert(
        self,
        collection_name: str,
        points: list[models.PointStruct],
        wait: bool = True,
    ) -> models.UpdateResult:
        store = self.points.setdefault(collection_name, {})
        for pt in points:
            store[str(pt.id)] = pt
        return models.UpdateResult(operation_id=1, status=models.UpdateStatus.COMPLETED)

    async def delete(
        self,
        collection_name: str,
        points_selector: models.Filter,
        wait: bool = True,
    ) -> models.UpdateResult:
        store = self.points.get(collection_name, {})
        to_delete: list[str] = []
        for pid, pt in store.items():
            payload = pt.payload or {}
            for condition in points_selector.must:
                if condition.key in payload and payload[condition.key] == condition.match.value:
                    to_delete.append(pid)
        for pid in to_delete:
            del store[pid]
        return models.UpdateResult(operation_id=2, status=models.UpdateStatus.COMPLETED)

    async def query_points(
        self,
        collection_name: str,
        query: list[float],
        query_filter: models.Filter | None = None,
        limit: int = 10,
        score_threshold: float | None = None,
        with_payload: bool = True,
    ) -> models.QueryResponse:
        store = self.points.get(collection_name, {})
        scored_points: list[models.ScoredPoint] = []

        for pt in store.values():
            payload = pt.payload or {}
            if query_filter:
                match = True
                for cond in query_filter.must:
                    if payload.get(cond.key) != cond.match.value:
                        match = False
                        break
                if not match:
                    continue

            score = _cosine_similarity(query, pt.vector)
            if score_threshold is not None and score < score_threshold:
                continue

            scored_points.append(
                models.ScoredPoint(
                    id=pt.id,
                    version=1,
                    score=score,
                    payload=payload if with_payload else None,
                    vector=None,
                )
            )

        scored_points.sort(key=lambda p: p.score, reverse=True)
        return SimpleNamespace(points=scored_points[:limit])  # type: ignore[return-value]

    async def close(self) -> None:

        pass


@pytest.mark.asyncio
async def test_end_to_end_chunk_embed_and_vector_store_pipeline():
    """Test full integration from chunked text to embedding generation and Qdrant storage."""
    doc_id = "doc-infrastructure-101"
    source_url = "https://example.com/ml-infra"

    # 1. Chunk document
    chunker = HybridMarkdownChunker(max_chunk_size=400, chunk_overlap=50)
    chunks = chunker.chunk(SAMPLE_DOCUMENT_MARKDOWN, metadata={"source_url": source_url})
    assert len(chunks) >= 3

    # Verify chunk properties
    for chunk in chunks:
        assert chunk.chunk_index >= 0
        assert chunk.text
        assert "heading_path" in chunk.metadata

    # 2. Mock Ollama embed endpoint with deterministic 1024-dim vectors
    # Construct distinct vectors where vector similarity correlates with topic keywords
    def embed_handler(request: httpx.Request) -> httpx.Response:
        import json

        data = json.loads(request.content)
        inputs: list[str] = data["input"]
        embeddings: list[list[float]] = []

        for text in inputs:
            vec = [0.01] * 1024
            if "Vector Search" in text or "HNSW" in text:
                vec[0] = 0.9  # Strongly signal vector search
            elif "Embedding Models" in text or "BGE-M3" in text:
                vec[1] = 0.9  # Strongly signal embeddings
            embeddings.append(vec)

        return httpx.Response(200, json={"model": "bge-m3", "embeddings": embeddings})

    transport = httpx.MockTransport(embed_handler)

    # 3. Generate embeddings
    async with httpx.AsyncClient(transport=transport) as http_client:
        embedding_client = OllamaEmbeddingClient(client=http_client, batch_size=2)
        chunk_texts = [c.text for c in chunks]
        vectors = await embedding_client.embed_batch(chunk_texts)

    assert len(vectors) == len(chunks)
    assert all(len(v) == 1024 for v in vectors)

    # 4. Upsert into Qdrant Vector Store
    simulated_qdrant = SimulatedQdrantClient()
    vector_store = QdrantVectorStore(client=simulated_qdrant)  # type: ignore[arg-type]

    await vector_store.initialize_collection()
    upserted_count = await vector_store.upsert_chunks(
        doc_id=doc_id,
        chunks=chunks,
        vectors=vectors,
        source_url=source_url,
    )
    assert upserted_count == len(chunks)
    assert len(simulated_qdrant.points["knowledge_base"]) == len(chunks)

    # 5. Search for Vector Search related content
    query_vector = [0.01] * 1024
    query_vector[0] = 0.9  # High similarity to vector search chunks

    search_results = await vector_store.search(
        query_vector=query_vector,
        limit=2,
        doc_id=doc_id,
    )
    assert len(search_results) >= 1
    top_hit = search_results[0]
    assert top_hit.score > 0.8
    assert top_hit.payload["doc_id"] == doc_id
    assert "Vector Search" in top_hit.payload["text"] or "HNSW" in top_hit.payload["text"]
    assert top_hit.payload["source_url"] == source_url

    # Verify deterministic UUID formatting
    expected_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc_id}:{top_hit.payload['chunk_index']}"))
    assert top_hit.point_id == expected_uuid

    # 6. Cascade delete by doc_id
    delete_result = await vector_store.delete_by_doc_id(doc_id=doc_id)
    assert delete_result >= 1
    assert len(simulated_qdrant.points["knowledge_base"]) == 0

    # 7. Verify search returns no results after deletion
    empty_search = await vector_store.search(
        query_vector=query_vector,
        limit=5,
        doc_id=doc_id,
    )
    assert len(empty_search) == 0


@pytest.mark.asyncio
async def test_live_vector_pipeline_if_available():
    """Verify end-to-end vector pipeline against live Ollama and Qdrant services if reachable."""
    from scripts.check_env import check_tcp_port

    ollama_ok = check_tcp_port(settings.ollama_host, settings.ollama_port)
    qdrant_ok = check_tcp_port(settings.qdrant_host, settings.qdrant_port)

    if not (ollama_ok and qdrant_ok):
        pytest.skip(f"Live services unreachable (Ollama: {ollama_ok}, Qdrant: {qdrant_ok}). Skipping live test.")

    # Live execution if services are online
    test_doc_id = f"test-live-{uuid.uuid4().hex[:8]}"
    test_text = "# Live Service Verification\n\nThis tests live Ollama and Qdrant containers."

    chunker = HybridMarkdownChunker()
    chunks = chunker.chunk(test_text)

    async with OllamaEmbeddingClient() as embed_client:
        vectors = await embed_client.embed_batch([c.text for c in chunks])

    async with QdrantVectorStore(collection_name="test_live_verification") as vector_store:
        await vector_store.initialize_collection()
        try:
            await vector_store.upsert_chunks(doc_id=test_doc_id, chunks=chunks, vectors=vectors)
            results = await vector_store.search(query_vector=vectors[0], limit=1, doc_id=test_doc_id)
            assert len(results) == 1
            assert results[0].payload["doc_id"] == test_doc_id
        finally:
            await vector_store.delete_by_doc_id(doc_id=test_doc_id)
