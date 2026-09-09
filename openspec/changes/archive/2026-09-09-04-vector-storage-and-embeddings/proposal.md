## Why

To support semantic search and RAG retrieval across varied document types, the pipeline requires a high-performance local embedding pipeline and vector store. Running the multilingual, 8192-token context `bge-m3` model locally via Ollama combined with Qdrant provides dense semantic vectors with sub-millisecond payload filtering and atomic cascade deletions.

## What Changes

- Implement `OllamaEmbeddingClient`:
  - Connects asynchronously to Ollama's HTTP API (`/api/embed`).
  - Generates 1024-dimensional dense vectors using the `bge-m3` model.
  - Implements batching, request timeout, and exponential backoff retry.
- Implement `QdrantVectorStore`:
  - Initializes the Qdrant collection (`knowledge_base`) with Cosine distance and 1024 dimensions.
  - Creates a keyword payload index on `doc_id` to enable instant filtered deletions.
  - Provides `upsert_chunks(doc_id, chunks, vectors)` to store points with rich payload metadata (chunk index, heading path, text, URL).
  - Provides `delete_document_vectors(doc_id)` to purge all points matching `doc_id`.
- Add integration tests verifying embedding generation against Ollama and point lifecycle in Qdrant.

## Capabilities

### New Capabilities
- `ollama-embeddings`: Client wrapper for local Ollama `bge-m3` embedding generation.
- `qdrant-vector-store`: Vector storage adapter managing Qdrant collection lifecycle, point upsert, and filtered deletion.

### Modified Capabilities
<!-- None -->

## Impact

- Completes the semantic storage layer required by the ingestion pipeline.
- Unblocks Phase 5 (Pipeline Service and Task Dispatcher).
