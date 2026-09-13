"""Asynchronous Ollama embedding client implementation."""

import asyncio
from types import TracebackType
from typing import Any, Self

import httpx

from app.core.config import settings
from app.core.exceptions import EmbeddingError


class OllamaEmbeddingClient:
    """Asynchronous client for generating embeddings via Ollama HTTP API."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        dimension: int = 1024,
        batch_size: int | None = None,
        timeout: float | None = None,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        raw_base_url = base_url or settings.ollama_base_url or "http://localhost:11434"
        self.base_url = raw_base_url.rstrip("/")
        self.model = model or settings.embedding_model or "bge-m3"
        self.dimension = dimension
        configured_batch_size = batch_size if batch_size is not None else getattr(settings, "embedding_batch_size", 8)
        self.batch_size = max(1, configured_batch_size)
        configured_timeout = timeout if timeout is not None else getattr(settings, "embedding_timeout", 120.0)
        self.timeout = configured_timeout
        self.max_retries = max(0, max_retries)
        self.backoff_factor = max(0.0, backoff_factor)
        self._client = client
        self._owns_client = client is None

    async def get_client(self) -> httpx.AsyncClient:
        """Get or initialize the underlying httpx AsyncClient."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
            self._owns_client = True
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client if owned by this instance."""
        if self._owns_client and self._client is not None and not self._client.is_closed:
            await self._client.aclose()

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

    async def embed_text(self, text: str) -> list[float]:
        """Generate a dense vector embedding for a single text string."""
        if not text or not text.strip():
            raise EmbeddingError("Text cannot be empty", model=self.model)
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate dense vector embeddings for a batch of text strings."""
        if not texts:
            return []
        for item in texts:
            if not item or not item.strip():
                raise EmbeddingError("Batch contains empty text string", model=self.model)

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            chunk = texts[i : i + self.batch_size]
            embeddings = await self._send_embed_request(chunk)
            all_embeddings.extend(embeddings)
        return all_embeddings

    async def _send_embed_request(self, texts: list[str]) -> list[list[float]]:
        """Send embedding request for a batch of texts and validate output."""
        payload = {"model": self.model, "input": texts}
        response_data = await self._post_with_retry(payload)
        return self._validate_embeddings(response_data, len(texts))

    async def _post_with_retry(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute POST request with exponential backoff for transient errors."""
        endpoint = f"{self.base_url}/api/embed"
        attempt = 0

        while True:
            http_client = await self.get_client()
            try:
                response = await http_client.post(endpoint, json=payload)
                if response.status_code == 200:
                    return response.json()
                self._handle_http_error(response, attempt)
            except httpx.RequestError as exc:
                if attempt >= self.max_retries:
                    raise EmbeddingError(
                        f"Failed to connect to Ollama after {self.max_retries} retries: {exc}",
                        model=self.model,
                    ) from exc

            delay = self.backoff_factor * (2**attempt)
            attempt += 1
            await asyncio.sleep(delay)

    def _handle_http_error(self, response: httpx.Response, attempt: int) -> None:
        """Evaluate HTTP status and raise or allow retry for 5xx/429."""
        status = response.status_code
        # Non-retriable 4xx client errors (except 429)
        if 400 <= status < 500 and status != 429:
            raise EmbeddingError(
                f"Ollama client error {status}: {response.text}",
                model=self.model,
                status_code=status,
            )
        # Server errors or rate limit
        if attempt == self.max_retries:
            raise EmbeddingError(
                f"Ollama server error {status} after {self.max_retries} retries: {response.text}",
                model=self.model,
                status_code=status,
            )

    def _validate_embeddings(
        self,
        data: dict[str, Any],
        expected_count: int,
    ) -> list[list[float]]:
        """Validate the structure and dimensions of returned embeddings."""
        raw_embeddings = data.get("embeddings")
        if not isinstance(raw_embeddings, list) or len(raw_embeddings) != expected_count:
            raise EmbeddingError(
                "Empty or invalid embeddings in response from Ollama",
                model=self.model,
            )

        validated: list[list[float]] = []
        for vec in raw_embeddings:
            if not isinstance(vec, list) or len(vec) != self.dimension:
                actual_len = len(vec) if isinstance(vec, list) else 0
                raise EmbeddingError(
                    f"Vector dimension mismatch: expected {self.dimension}, got {actual_len}",
                    model=self.model,
                )
            validated.append([float(v) for v in vec])
        return validated
