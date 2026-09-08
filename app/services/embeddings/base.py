"""Base protocols for embedding clients."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class BaseEmbeddingClient(Protocol):
    """Protocol defining asynchronous embedding client interface."""

    async def embed_text(self, text: str) -> list[float]:
        """Generate a dense vector embedding for a single text string.

        Args:
            text: Input text string to embed.

        Returns:
            List of float values representing the dense embedding vector.
        """
        ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate dense vector embeddings for a batch of text strings.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of dense embedding vectors in the same order as input texts.
        """
        ...
