## Context

See `proposal.md` for motivation. Phase 1 set up local backing services (including Qdrant on port 6333 and Ollama on port 11434), Phase 2 implemented the PostgreSQL metadata repository, and Phase 3 completed the Crawl4AI extractor and Hybrid Markdown chunker. In this phase, we implement the semantic layer: an asynchronous Ollama client for local `bge-m3` vector embeddings and a Qdrant vector storage adapter supporting collection management, point upserts with rich metadata, and instant filtered deletions by `doc_id`.

## Goals / Non-Goals

**Goals:**
- Implement `OllamaEmbeddingClient` in `app/services/embeddings/ollama.py` using `httpx.AsyncClient` with configurable batching, retry with exponential backoff, and dimension validation (1024).
- Implement `QdrantVectorStore` in `app/services/vector_store/qdrant.py` using `qdrant_client.AsyncQdrantClient`:
  - Idempotent collection initialization (`knowledge_base`, Cosine, 1024-dim).
  - Keyword payload indexing on `doc_id`.
  - Batch point upsert with deterministic UUIDs (`uuid5` on `doc_id` and `chunk_index`).
  - Filtered deletion of all points matching `doc_id`.
  - Vector similarity search with payload and score retrieval.
- Unit and integration tests validating embedding calls, dimension validation, retry logic, and Qdrant vector operations using mocks and container integration tests.

**Non-Goals:**
- Queue or background worker execution (deferred to Phase 5).
- Ingestion pipeline service orchestration (deferred to Phase 5).
- Exposing REST API endpoints (deferred to Phase 6).

## Decisions

### Decision: Direct Asynchronous HTTP Client for Ollama
- **Rationale**: Ollama exposes a simple, high-performance `/api/embed` endpoint. Using `httpx.AsyncClient` keeps our dependencies lean, avoids heavy third-party SDKs, and allows fine-grained control over connection pooling, timeouts, and backoff retries.
- **Alternatives considered**: Official `ollama` Python SDK (adds unnecessary external abstraction layer) or in-process `FlagEmbedding`/`sentence-transformers` (heavy PyTorch footprint in worker process).

### Decision: AsyncQdrantClient for Vector Operations
- **Rationale**: `qdrant-client` provides first-class async support (`AsyncQdrantClient`). It integrates seamlessly with FastAPI and our async services without thread-pool overhead.
- **Alternatives considered**: Synchronous `QdrantClient` in `asyncio.to_thread` (less efficient, extra thread synchronization overhead).

### Decision: Deterministic Point UUIDs for Idempotent Upserts
- **Rationale**: Generating point UUIDs via `uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc_id}:{chunk_index}")` guarantees idempotency. If an upsert is retried, existing points are updated in place rather than duplicated.
- **Alternatives considered**: Random `uuid4()` for every point (creates duplicates on retried upserts).

### Decision: Keyword Payload Indexing on `doc_id`
- **Rationale**: Qdrant's payload index allows `delete` operations with a filter (`FieldCondition(key="doc_id", match=MatchValue(value=doc_id))`) to execute in sub-milliseconds without scanning the full collection.
- **Alternatives considered**: Tracking point IDs in PostgreSQL and deleting by ID list (unnecessary schema coupling and extra DB roundtrips).

## Risks / Trade-offs

- **[Risk] Ollama Unavailability or Model Not Pulled**: If the Ollama service is not running or `bge-m3` has not been pulled, embedding calls will fail.
  - *Mitigation*: Provide clear domain exception messages (`EmbeddingError`) and verify connectivity via `check_env.py`.
- **[Risk] Request Payload Size Limits in Ollama**: Sending hundreds of text chunks in a single request could cause HTTP request timeouts or OOM on CPU/GPU.
  - *Mitigation*: Chunk the embedding requests into batches (default: 16 chunks per request) with configurable concurrency.
