"""Unit tests for embedding clients and exceptions."""

import pytest
from app.core.exceptions import EmbeddingError, PipelineError
from app.services.embeddings.base import BaseEmbeddingClient


def test_embedding_error_attributes_and_hierarchy() -> None:
    """Test EmbeddingError attributes, default values, and inheritance hierarchy."""
    err = EmbeddingError(
        "Model failure",
        model="bge-m3",
        status_code=500,
    )
    assert isinstance(err, PipelineError)
    assert isinstance(err, Exception)
    assert str(err) == "Model failure"
    assert err.model == "bge-m3"
    assert err.status_code == 500


def test_embedding_error_defaults() -> None:
    """Test EmbeddingError default optional attributes."""
    err = EmbeddingError("Generic embedding failure")
    assert str(err) == "Generic embedding failure"
    assert err.model is None
    assert err.status_code is None


def test_base_embedding_client_protocol() -> None:
    """Test BaseEmbeddingClient protocol compliance."""
    from app.services.embeddings.base import BaseEmbeddingClient

    class ValidClient:
        async def embed_text(self, text: str) -> list[float]:
            return [0.1] * 1024

        async def embed_batch(self, texts: list[str]) -> list[list[float]]:
            return [[0.1] * 1024 for _ in texts]

    class IncompleteClient:
        async def embed_text(self, text: str) -> list[float]:
            return [0.1] * 1024

    assert isinstance(ValidClient(), BaseEmbeddingClient)
    assert not isinstance(IncompleteClient(), BaseEmbeddingClient)


@pytest.mark.asyncio
async def test_ollama_client_protocol_conformance() -> None:
    """Test OllamaEmbeddingClient conforms to BaseEmbeddingClient protocol."""
    from app.services.embeddings.ollama import OllamaEmbeddingClient

    client = OllamaEmbeddingClient()
    assert isinstance(client, BaseEmbeddingClient)
    await client.close()


def test_ollama_client_init_defaults() -> None:
    """Test OllamaEmbeddingClient initialization with default settings."""
    from app.core.config import settings
    from app.services.embeddings.ollama import OllamaEmbeddingClient

    client = OllamaEmbeddingClient()
    assert client.base_url == settings.ollama_base_url.rstrip("/")
    assert client.model == settings.embedding_model
    assert client.dimension == 1024
    assert client.batch_size == 8
    assert client.timeout == 120.0
    assert client.max_retries == 3
    assert client.backoff_factor == 0.5


@pytest.mark.asyncio
async def test_ollama_client_init_custom_and_context_manager() -> None:
    """Test OllamaEmbeddingClient with custom configuration and context manager lifecycle."""
    import httpx
    from app.services.embeddings.ollama import OllamaEmbeddingClient

    custom_http_client = httpx.AsyncClient()
    try:
        async with OllamaEmbeddingClient(
            base_url="http://custom-host:12345/",
            model="custom-model",
            dimension=512,
            batch_size=8,
            timeout=15.0,
            max_retries=5,
            backoff_factor=0.1,
            client=custom_http_client,
        ) as client:
            assert client.base_url == "http://custom-host:12345"
            assert client.model == "custom-model"
            assert client.dimension == 512
            assert client.batch_size == 8
            assert client.timeout == 15.0
            assert client.max_retries == 5
            assert client.backoff_factor == 0.1
            internal_client = await client.get_client()
            assert internal_client is custom_http_client
            assert not internal_client.is_closed

        # Since custom client was injected, client.close() does not close injected client
        assert not custom_http_client.is_closed
    finally:
        await custom_http_client.aclose()


@pytest.mark.asyncio
async def test_ollama_client_owns_client_close() -> None:
    """Test OllamaEmbeddingClient creates and closes its own HTTP client."""
    from app.services.embeddings.ollama import OllamaEmbeddingClient

    client = OllamaEmbeddingClient()
    http_client = await client.get_client()
    assert not http_client.is_closed
    await client.close()
    assert http_client.is_closed


@pytest.mark.asyncio
async def test_embed_text_success() -> None:
    """Test successful single text embedding with 1024 dimensions."""
    import httpx
    from app.services.embeddings.ollama import OllamaEmbeddingClient

    expected_vector = [0.05 * (i % 10) for i in range(1024)]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://localhost:11434/api/embed"
        assert request.method == "POST"
        import json

        payload = json.loads(request.content)
        assert payload["model"] == "bge-m3"
        assert payload["input"] == ["Sample text chunk"]
        return httpx.Response(
            200,
            json={"model": "bge-m3", "embeddings": [expected_vector]},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OllamaEmbeddingClient(client=http_client)
        vector = await client.embed_text("Sample text chunk")
        assert len(vector) == 1024
        assert vector == expected_vector


@pytest.mark.asyncio
async def test_embed_text_dimension_mismatch() -> None:
    """Test that embedding response with mismatched dimensions raises EmbeddingError."""
    import httpx
    from app.services.embeddings.ollama import OllamaEmbeddingClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"model": "bge-m3", "embeddings": [[0.1] * 512]},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OllamaEmbeddingClient(client=http_client, dimension=1024)
        with pytest.raises(EmbeddingError, match="expected 1024, got 512"):
            await client.embed_text("Sample text")


@pytest.mark.asyncio
async def test_embed_text_empty_string_raises() -> None:
    """Test that empty or whitespace-only text raises EmbeddingError."""
    from app.services.embeddings.ollama import OllamaEmbeddingClient

    client = OllamaEmbeddingClient()
    with pytest.raises(EmbeddingError, match="Text cannot be empty"):
        await client.embed_text("   ")


@pytest.mark.asyncio
async def test_embed_text_malformed_response() -> None:
    """Test that malformed embedding responses raise EmbeddingError."""
    import httpx
    from app.services.embeddings.ollama import OllamaEmbeddingClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": "bge-m3", "embeddings": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OllamaEmbeddingClient(client=http_client)
        with pytest.raises(EmbeddingError, match="Empty or invalid embeddings in response"):
            await client.embed_text("Sample text")


@pytest.mark.asyncio
async def test_embed_batch_empty_list() -> None:
    """Test embed_batch with empty list returns empty list immediately."""
    from app.services.embeddings.ollama import OllamaEmbeddingClient

    client = OllamaEmbeddingClient()
    result = await client.embed_batch([])
    assert result == []


@pytest.mark.asyncio
async def test_embed_batch_with_blank_string_raises() -> None:
    """Test embed_batch raises EmbeddingError if any item in batch is blank."""
    from app.services.embeddings.ollama import OllamaEmbeddingClient

    client = OllamaEmbeddingClient()
    with pytest.raises(EmbeddingError, match="Batch contains empty text string"):
        await client.embed_batch(["valid text", "   ", "another valid"])


@pytest.mark.asyncio
async def test_embed_batch_multiple_chunks_batching_and_order() -> None:
    """Test batch embedding groups requests according to batch_size and preserves order."""
    import json

    import httpx
    from app.services.embeddings.ollama import OllamaEmbeddingClient

    texts = [f"Text chunk {i}" for i in range(5)]
    recorded_batches: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        data = json.loads(request.content)
        chunk_inputs = data["input"]
        recorded_batches.append(chunk_inputs)
        # Return a deterministic vector for each input
        mock_embeddings = [[float(i)] * 1024 for i in range(len(chunk_inputs))]
        return httpx.Response(200, json={"model": "bge-m3", "embeddings": mock_embeddings})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OllamaEmbeddingClient(
            client=http_client,
            batch_size=2,  # Should split 5 items into [2, 2, 1]
        )
        vectors = await client.embed_batch(texts)

        assert len(recorded_batches) == 3
        assert recorded_batches[0] == ["Text chunk 0", "Text chunk 1"]
        assert recorded_batches[1] == ["Text chunk 2", "Text chunk 3"]
        assert recorded_batches[2] == ["Text chunk 4"]
        assert len(vectors) == 5


@pytest.mark.asyncio
async def test_embed_retry_on_5xx_and_eventual_success() -> None:
    """Test retry mechanism on 500 error that succeeds on subsequent attempt."""
    import httpx
    from app.services.embeddings.ollama import OllamaEmbeddingClient

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(503, text="Service Unavailable")
        return httpx.Response(200, json={"model": "bge-m3", "embeddings": [[0.5] * 1024]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OllamaEmbeddingClient(
            client=http_client,
            max_retries=3,
            backoff_factor=0.01,
        )
        vector = await client.embed_text("Retry success text")
        assert len(vector) == 1024
        assert call_count == 3


@pytest.mark.asyncio
async def test_embed_retry_exhaustion_5xx_raises_embedding_error() -> None:
    """Test retry exhaustion on persistent 500 raises EmbeddingError with status code."""
    import httpx
    from app.services.embeddings.ollama import OllamaEmbeddingClient

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(500, text="Internal Server Error")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OllamaEmbeddingClient(
            client=http_client,
            max_retries=2,
            backoff_factor=0.01,
        )
        with pytest.raises(EmbeddingError) as exc_info:
            await client.embed_text("Failing text")

        assert "Ollama server error 500" in str(exc_info.value)
        assert exc_info.value.status_code == 500
        assert exc_info.value.model == "bge-m3"
        assert call_count == 3  # Initial attempt + 2 retries


@pytest.mark.asyncio
async def test_embed_non_retriable_4xx_raises_immediately() -> None:
    """Test non-retriable 4xx client errors fail immediately without retry."""
    import httpx
    from app.services.embeddings.ollama import OllamaEmbeddingClient

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(404, text="model 'unknown-model' not found")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OllamaEmbeddingClient(
            client=http_client,
            max_retries=3,
            backoff_factor=0.01,
        )
        with pytest.raises(EmbeddingError) as exc_info:
            await client.embed_text("Non-existent model text")

        assert "Ollama client error 404" in str(exc_info.value)
        assert exc_info.value.status_code == 404
        assert call_count == 1  # No retries for 404


@pytest.mark.asyncio
async def test_embed_retry_on_network_error_and_eventual_success() -> None:
    """Test retry on transport/network error that succeeds on subsequent attempt."""
    import httpx
    from app.services.embeddings.ollama import OllamaEmbeddingClient

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise httpx.ConnectError("Connection refused")
        return httpx.Response(200, json={"model": "bge-m3", "embeddings": [[0.7] * 1024]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OllamaEmbeddingClient(
            client=http_client,
            max_retries=2,
            backoff_factor=0.01,
        )
        vector = await client.embed_text("Connection recovery text")
        assert len(vector) == 1024
        assert call_count == 2


@pytest.mark.asyncio
async def test_embed_retry_exhaustion_on_network_error() -> None:
    """Test retry exhaustion on persistent transport errors raises EmbeddingError."""
    import httpx
    from app.services.embeddings.ollama import OllamaEmbeddingClient

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectError("Host unreachable")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OllamaEmbeddingClient(
            client=http_client,
            max_retries=2,
            backoff_factor=0.01,
        )
        with pytest.raises(EmbeddingError) as exc_info:
            await client.embed_text("Unreachable host text")

        assert "Failed to connect to Ollama after 2 retries" in str(exc_info.value)
        assert call_count == 3


@pytest.mark.asyncio
async def test_embed_rate_limit_429_triggers_retry() -> None:
    """Test HTTP 429 triggers backoff retry and succeeds."""
    import httpx
    from app.services.embeddings.ollama import OllamaEmbeddingClient

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429, text="Too Many Requests")
        return httpx.Response(200, json={"model": "bge-m3", "embeddings": [[0.2] * 1024]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OllamaEmbeddingClient(
            client=http_client,
            max_retries=2,
            backoff_factor=0.01,
        )
        vector = await client.embed_text("Rate limited then success")
        assert len(vector) == 1024
        assert call_count == 2


@pytest.mark.asyncio
async def test_validate_embeddings_non_list_in_embeddings() -> None:
    """Test validation when an element inside embeddings is not a list."""
    import httpx
    from app.services.embeddings.ollama import OllamaEmbeddingClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": "bge-m3", "embeddings": ["not a vector"]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OllamaEmbeddingClient(client=http_client)
        with pytest.raises(EmbeddingError, match="Vector dimension mismatch"):
            await client.embed_text("Some text")
