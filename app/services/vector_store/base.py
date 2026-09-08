"""Base models and protocols for vector store adapters."""

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from app.services.chunkers.base import DocumentChunk


class VectorSearchResult(BaseModel):
    """Result of a vector similarity search."""

    model_config = ConfigDict(frozen=True)

    point_id: str = Field(description="Unique point UUID string")
    score: float = Field(description="Similarity score")
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Point metadata payload",
    )


@runtime_checkable
class BaseVectorStore(Protocol):
    """Protocol defining vector storage operations."""

    async def initialize_collection(self) -> None:
        """Initialize collection and payload indexes if not already present."""
        ...

    async def upsert_chunks(
        self,
        doc_id: str,
        chunks: list[DocumentChunk],
        vectors: list[list[float]],
        source_url: str | None = None,
    ) -> int:
        """Upsert document chunks and corresponding vectors into vector store.

        Args:
            doc_id: Unique document identifier.
            chunks: List of DocumentChunk instances.
            vectors: Corresponding dense embedding vectors.
            source_url: Optional source URL of the document.

        Returns:
            Number of points successfully upserted.
        """
        ...

    async def delete_by_doc_id(self, doc_id: str) -> int:
        """Delete all points associated with a specific document ID.

        Args:
            doc_id: Unique document identifier.

        Returns:
            Number of points or deletion operations performed.
        """
        ...

    async def search(
        self,
        query_vector: list[float],
        limit: int = 5,
        doc_id: str | None = None,
        score_threshold: float | None = None,
    ) -> list[VectorSearchResult]:
        """Perform vector similarity search.

        Args:
            query_vector: Query embedding vector.
            limit: Maximum number of search results to return.
            doc_id: Optional filter by specific document ID.
            score_threshold: Optional minimum similarity score threshold.

        Returns:
            List of VectorSearchResult objects ordered by descending score.
        """
        ...
