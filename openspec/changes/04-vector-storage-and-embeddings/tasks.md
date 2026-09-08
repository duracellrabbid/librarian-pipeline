## 1. Ollama Embedding Client

- [x] 1.1 Define `EmbeddingError` domain exception in `app/core/exceptions.py`.
- [x] 1.2 Define `BaseEmbeddingClient` protocol in `app/services/embeddings/base.py`.
- [x] 1.3 Implement `OllamaEmbeddingClient` in `app/services/embeddings/ollama.py` utilizing `httpx.AsyncClient` to query Ollama's `/api/embed` endpoint for the `bge-m3` model.
- [x] 1.4 Implement batch processing and retry with exponential backoff for transient HTTP/connection errors in `OllamaEmbeddingClient`.
- [x] 1.5 Write unit tests in `tests/test_embeddings.py` verifying single text embedding, batch processing, vector dimension validation (1024), and retry/error handling with mocked HTTP responses.


## 2. Qdrant Vector Store Adapter

- [x] 2.1 Define `VectorStoreError` domain exception in `app/core/exceptions.py`.
- [x] 2.2 Define `BaseVectorStore` protocol in `app/services/vector_store/base.py`.
- [x] 2.3 Implement `QdrantVectorStore` in `app/services/vector_store/qdrant.py` with idempotent collection creation (`knowledge_base`, Cosine distance, 1024 dimensions) and `doc_id` keyword payload index creation.
- [x] 2.4 Implement `upsert_chunks()` in `QdrantVectorStore` using deterministic point UUIDs (`uuid5`) and comprehensive payload fields (`doc_id`, `chunk_index`, `text`, `source_url`, `heading_path`).
- [x] 2.5 Implement `delete_by_doc_id()` in `QdrantVectorStore` using payload filter conditions to purge all points matching the given document ID.
- [x] 2.6 Implement `search()` in `QdrantVectorStore` returning top-k nearest chunks with similarity scores and payloads.
- [x] 2.7 Write unit tests in `tests/test_vector_store.py` verifying collection creation, point upsert, filtered deletion, and similarity search using mocked Qdrant client.

## 3. Integration Testing & Documentation

- [x] 3.1 Write integration test connecting chunked document output to `OllamaEmbeddingClient` and `QdrantVectorStore`, verifying end-to-end vector upsert, search, and cascade deletion by `doc_id`.
- [x] 3.2 Update `README.md` with Ollama `bge-m3` configuration details, Qdrant collection specifications, and integration test instructions.


