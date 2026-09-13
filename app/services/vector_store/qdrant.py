"""Asynchronous Qdrant vector store adapter."""

import uuid
from types import TracebackType
from typing import Any, Self

from qdrant_client import AsyncQdrantClient, models

from app.core.config import settings
from app.core.exceptions import VectorStoreError
from app.services.chunkers.base import DocumentChunk
from app.services.vector_store.base import VectorSearchResult


class QdrantVectorStore:
    """Asynchronous vector storage adapter managing Qdrant operations."""

    def __init__(
        self,
        collection_name: str = "knowledge_base",
        dimension: int = 1024,
        url: str | None = None,
        api_key: str | None = None,
        client: AsyncQdrantClient | None = None,
    ) -> None:
        self.collection_name = collection_name
        self.dimension = dimension
        self.url = url or settings.qdrant_url
        raw_key = api_key if api_key is not None else settings.qdrant_api_key
        self.api_key = raw_key.strip() if raw_key and raw_key.strip() else None
        self._client = client
        self._owns_client = client is None

    async def get_client(self) -> AsyncQdrantClient:
        """Get or initialize the underlying AsyncQdrantClient."""
        if self._client is None:
            self._client = AsyncQdrantClient(url=self.url, api_key=self.api_key)
            self._owns_client = True
        return self._client

    async def close(self) -> None:
        """Close the underlying client if owned by this instance."""
        if self._owns_client and self._client is not None:
            await self._client.close()

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        await self.get_client()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit."""
        await self.close()

    async def initialize_collection(self) -> None:
        """Idempotently create collection and doc_id keyword index."""
        client = await self.get_client()
        try:
            exists = await client.collection_exists(self.collection_name)
            if not exists:
                await client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=self.dimension,
                        distance=models.Distance.COSINE,
                    ),
                )

            info = await client.get_collection(self.collection_name)
            payload_schema = info.payload_schema or {}
            if "doc_id" not in payload_schema:
                await client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="doc_id",
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
        except Exception as exc:
            raise VectorStoreError(
                f"Failed to initialize Qdrant collection '{self.collection_name}': {exc}",
                collection_name=self.collection_name,
            ) from exc

    async def upsert_chunks(
        self,
        doc_id: str,
        chunks: list[DocumentChunk],
        vectors: list[list[float]],
        source_url: str | None = None,
    ) -> int:
        """Upsert document chunks and vectors into Qdrant."""
        self._validate_upsert_inputs(doc_id, chunks, vectors)
        if not chunks:
            return 0

        points = [
            self._build_point(doc_id, chunk, vector, source_url) for chunk, vector in zip(chunks, vectors, strict=True)
        ]

        client = await self.get_client()
        try:
            await client.upsert(
                collection_name=self.collection_name,
                points=points,
                wait=True,
            )
            return len(points)
        except Exception as exc:
            raise VectorStoreError(
                f"Failed to upsert chunks to Qdrant: {exc}",
                collection_name=self.collection_name,
            ) from exc

    def _validate_upsert_inputs(
        self,
        doc_id: str,
        chunks: list[DocumentChunk],
        vectors: list[list[float]],
    ) -> None:
        """Validate input parameters for upsert operation."""
        if not doc_id or not doc_id.strip():
            raise VectorStoreError(
                "doc_id cannot be empty",
                collection_name=self.collection_name,
            )
        if len(chunks) != len(vectors):
            raise VectorStoreError(
                f"Chunks count ({len(chunks)}) does not match vectors count ({len(vectors)})",
                collection_name=self.collection_name,
            )
        for vec in vectors:
            if len(vec) != self.dimension:
                raise VectorStoreError(
                    f"Vector dimension mismatch: expected {self.dimension}, got {len(vec)}",
                    collection_name=self.collection_name,
                )

    def _build_point(
        self,
        doc_id: str,
        chunk: DocumentChunk,
        vector: list[float],
        source_url: str | None,
    ) -> models.PointStruct:
        """Construct deterministic PointStruct with metadata payload."""
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc_id}:{chunk.chunk_index}"))
        resolved_url = source_url or chunk.metadata.get("source_url")
        heading_path = chunk.metadata.get("heading_path", [])

        payload: dict[str, Any] = {
            "doc_id": doc_id,
            "chunk_index": chunk.chunk_index,
            "text": chunk.text,
            "source_url": resolved_url,
            "heading_path": heading_path,
            "char_count": chunk.char_count,
            "token_count": chunk.token_count,
        }
        for key, val in chunk.metadata.items():
            if key not in payload:
                payload[key] = val

        return models.PointStruct(
            id=point_id,
            vector=vector,
            payload=payload,
        )

    async def delete_by_doc_id(self, doc_id: str) -> int:
        """Delete all points matching doc_id from Qdrant."""
        if not doc_id or not doc_id.strip():
            raise VectorStoreError(
                "doc_id cannot be empty",
                collection_name=self.collection_name,
            )

        client = await self.get_client()
        try:
            await client.delete(
                collection_name=self.collection_name,
                points_selector=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="doc_id",
                            match=models.MatchValue(value=doc_id),
                        )
                    ]
                ),
                wait=True,
            )
            return 1
        except Exception as exc:
            raise VectorStoreError(
                f"Failed to delete points for doc_id '{doc_id}': {exc}",
                collection_name=self.collection_name,
            ) from exc

    async def search(
        self,
        query_vector: list[float],
        limit: int = 5,
        doc_id: str | None = None,
        score_threshold: float | None = None,
    ) -> list[VectorSearchResult]:
        """Search nearest points using query vector."""
        if len(query_vector) != self.dimension:
            raise VectorStoreError(
                f"Query vector dimension mismatch: expected {self.dimension}, got {len(query_vector)}",
                collection_name=self.collection_name,
            )

        query_filter: models.Filter | None = None
        if doc_id:
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="doc_id",
                        match=models.MatchValue(value=doc_id),
                    )
                ]
            )

        client = await self.get_client()
        try:
            response = await client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=max(1, limit),
                score_threshold=score_threshold,
                with_payload=True,
            )
            return [
                VectorSearchResult(
                    point_id=str(point.id),
                    score=float(point.score),
                    payload=point.payload or {},
                )
                for point in response.points
            ]
        except Exception as exc:
            raise VectorStoreError(
                f"Vector search failed: {exc}",
                collection_name=self.collection_name,
            ) from exc
