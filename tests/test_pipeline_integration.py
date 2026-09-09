"""Headless integration tests for the end-to-end ingestion pipeline."""

import hashlib
import math
from types import SimpleNamespace
from typing import Any

import pytest
from app.models.document import Document
from app.models.job import IngestionJob, JobStatus
from app.services.chunkers.hybrid import HybridMarkdownChunker
from app.services.extractors.base import ExtractedDocument
from app.services.pipeline import IngestionPipelineService
from app.services.repository import create_document_and_job
from app.services.vector_store.qdrant import QdrantVectorStore
from qdrant_client import models
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select

SAMPLE_INTEGRATION_MARKDOWN = """# High Performance RAG Pipelines

Building scalable retrieval-augmented generation systems requires decoupled indexing.

## Document Processing

Extracting clean markdown preserves headings, links, and document layout.
Hybrid chunking segments content while preserving semantic breadcrumbs.

### Vector Storage

Qdrant indexes dense vectors with payload filters for tenant and document isolation.
Cosine similarity over BGE-M3 1024-dimensional embeddings enables high-accuracy retrieval.
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
    """In-memory simulated AsyncQdrantClient for headless integration testing."""

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

    async def query_points(
        self,
        collection_name: str,
        query: list[float],
        query_filter: models.Filter | None = None,
        limit: int = 10,
        score_threshold: float | None = None,
        with_payload: bool = True,
    ) -> Any:
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
        return SimpleNamespace(points=scored_points[:limit])

    async def close(self) -> None:
        pass


class DeterministicEmbeddingClient:
    """Deterministic embedding client producing pseudo-embeddings for headless tests."""

    async def embed_text(self, text: str) -> list[float]:
        # Generate 1024-dim deterministic normalized vector from text hash
        val = sum(ord(c) for c in text) % 1000 / 1000.0
        vec = [val + (i / 10000.0) for i in range(1024)]
        norm = math.sqrt(sum(x * x for x in vec))
        return [x / norm for x in vec]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed_text(t) for t in texts]


class MockContentExtractor:
    """Mock extractor returning structured markdown content."""

    def __init__(self, content: str, title: str) -> None:
        self.content = content
        self.title = title

    async def extract(self, source: str) -> ExtractedDocument:
        return ExtractedDocument(
            content=self.content,
            title=self.title,
            source_url=source,
            metadata={"extracted": True},
        )


@pytest.fixture
async def in_memory_db():
    """Create a shared SQLite in-memory database with StaticPool."""
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

    yield session_factory

    await engine.dispose()


@pytest.mark.asyncio
async def test_headless_end_to_end_pipeline_integration(in_memory_db):
    """Verify the full pipeline executes from job creation to DB and vector store verification."""
    url = "https://example.com/high-perf-rag"
    title = "High Performance RAG Pipelines"

    # 1. Initialize backing mock/simulated services
    simulated_qdrant = SimulatedQdrantClient()
    vector_store = QdrantVectorStore(client=simulated_qdrant, collection_name="test_integration")
    await vector_store.initialize_collection()

    chunker = HybridMarkdownChunker(max_chunk_size=300, chunk_overlap=30)
    embedding_client = DeterministicEmbeddingClient()
    extractor = MockContentExtractor(SAMPLE_INTEGRATION_MARKDOWN, title)

    # 2. Register document and job in PostgreSQL (SQLite in test) via repository
    async with in_memory_db() as init_session:
        doc, job = await create_document_and_job(
            session=init_session,
            source_type="url",
            source_url=url,
        )
        assert job.status == JobStatus.PENDING.value
        assert job.progress_percentage == 0
        assert doc.chunk_count == 0
        assert doc.title is None
        job_id = job.id
        doc_id = doc.id

    # 3. Instantiate and run IngestionPipelineService
    pipeline_service = IngestionPipelineService(
        extractor=extractor,
        chunker=chunker,
        embedding_client=embedding_client,
        vector_store=vector_store,
        session_factory=in_memory_db,
    )

    await pipeline_service.run(
        job_id=job_id,
        document_id=doc_id,
        url=url,
    )

    # 4. Verify Database State
    async with in_memory_db() as verify_session:
        doc_stmt = select(Document).where(Document.id == doc_id)
        doc_res = await verify_session.execute(doc_stmt)
        updated_doc = doc_res.scalars().one()

        assert updated_doc.title == title
        assert updated_doc.chunk_count > 0
        expected_hash = hashlib.sha256(SAMPLE_INTEGRATION_MARKDOWN.encode("utf-8")).hexdigest()
        assert updated_doc.content_hash == expected_hash
        assert updated_doc.updated_at is not None

        job_stmt = select(IngestionJob).where(IngestionJob.id == job_id)
        job_res = await verify_session.execute(job_stmt)
        updated_job = job_res.scalars().one()

        assert updated_job.status == JobStatus.INDEXED.value
        assert updated_job.progress_percentage == 100
        assert updated_job.error_message is None
        assert updated_job.finished_at is not None

    # 5. Verify Vector Store State
    query_vector = await embedding_client.embed_text("retrieval augmented generation")
    search_results = await vector_store.search(
        query_vector=query_vector,
        limit=5,
        doc_id=str(doc_id),
    )

    assert len(search_results) > 0
    assert search_results[0].payload["doc_id"] == str(doc_id)
    assert search_results[0].payload["source_url"] == url
    assert "chunk_index" in search_results[0].payload


@pytest.mark.asyncio
async def test_headless_pipeline_integration_failure_recovery(in_memory_db):
    """Verify that failure during pipeline execution marks the job as FAILED with error message."""
    url = "https://example.com/broken-url"

    simulated_qdrant = SimulatedQdrantClient()
    vector_store = QdrantVectorStore(client=simulated_qdrant, collection_name="test_integration")
    await vector_store.initialize_collection()

    class FailingExtractor:
        async def extract(self, source: str) -> ExtractedDocument:
            raise ConnectionError("Upstream web server connection reset")

    async with in_memory_db() as init_session:
        doc, job = await create_document_and_job(
            session=init_session,
            source_type="url",
            source_url=url,
        )
        job_id = job.id
        doc_id = doc.id

    pipeline_service = IngestionPipelineService(
        extractor=FailingExtractor(),
        chunker=HybridMarkdownChunker(),
        embedding_client=DeterministicEmbeddingClient(),
        vector_store=vector_store,
        session_factory=in_memory_db,
    )

    await pipeline_service.run(job_id=job_id, document_id=doc_id, url=url)

    async with in_memory_db() as verify_session:
        job_stmt = select(IngestionJob).where(IngestionJob.id == job_id)
        job_res = await verify_session.execute(job_stmt)
        failed_job = job_res.scalars().one()

        assert failed_job.status == JobStatus.FAILED.value
        assert "ConnectionError" in (failed_job.error_message or "")
        assert "connection reset" in (failed_job.error_message or "")
        assert failed_job.finished_at is not None
