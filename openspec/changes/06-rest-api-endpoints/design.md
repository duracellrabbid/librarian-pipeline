## Context

See `proposal.md` for motivation. With Phases 1 through 5 completed, all foundational subsystems exist: PostgreSQL models/repositories, Crawl4AI web extraction, Hybrid Markdown chunking, Ollama `bge-m3` embedding, Qdrant vector storage, ARQ task dispatching, and `IngestionPipelineService`. In this final phase, we expose these capabilities through a clean, validated FastAPI REST API with the 4 required endpoints.

## Goals / Non-Goals

**Goals:**
- Implement FastAPI application entry point in `app/main.py` with lifespan event handlers, CORS, and standard JSON exception handlers.
- Define request and response Pydantic schemas in `app/api/schemas.py`:
  - `IngestRequest`, `IngestResponse`
  - `JobStatusResponse`
  - `DocumentCheckResponse`
  - `DeleteResponse`
- Implement route handlers in `app/api/v1/endpoints/documents.py`:
  - `POST /documents/ingest` (returns 202 Accepted or 409 Conflict)
  - `GET /documents/status/{job_id}` (returns 200 OK or 404 Not Found)
  - `GET /documents/check` (returns 200 OK with existence and doc_id)
  - `DELETE /documents/{doc_id}` (returns 200 OK or 404 Not Found)
- Wire dependency injection for database sessions, `TaskDispatcher`, and `QdrantVectorStore` via FastAPI `Depends`.
- Integration tests using `httpx.AsyncClient` covering all happy paths and error cases (duplicate 409, not found 404, invalid URLs 422).

**Non-Goals:**
- Authentication / Authorization (API keys, OAuth2) - deferred to future scope.
- Hard delete endpoint - deferred to future scope.
- Advanced rate limiting or throttling.

## Decisions

### Decision: Semantic HTTP Status Codes
- **Rationale**:
  - `POST /documents/ingest`: Returns `202 Accepted` since ingestion is asynchronous, or `409 Conflict` if the URL is actively ingested.
  - `GET /documents/status/{job_id}`: Returns `200 OK` or `404 Not Found` if the job does not exist.
  - `GET /documents/check`: Always returns `200 OK` with a structured `{ "exists": bool, ... }` payload.
  - `DELETE /documents/{doc_id}`: Returns `200 OK` or `404 Not Found` if the document is not active.
- **Alternatives considered**: Returning `200 OK` for ingestion (misleads clients into thinking ingestion is already finished synchronously).

### Decision: Dependency Injection via FastAPI `Depends`
- **Rationale**: Routes declare dependencies (`session: AsyncSession = Depends(get_async_session)`, `dispatcher: TaskDispatcher = Depends(get_dispatcher)`, `vector_store: BaseVectorStore = Depends(get_vector_store)`). In test suites, these dependencies can be swapped via `app.dependency_overrides` without monkeypatching global objects.
- **Alternatives considered**: Directly referencing global singletons in route functions (makes unit and mock testing brittle).

### Decision: Concurrency Protection on Ingestion
- **Rationale**: In addition to application-level checking via `check_active_url`, PostgreSQL's unique partial index (`UNIQUE (source_url) WHERE deleted_at IS NULL`) guarantees that concurrent requests with identical URLs cannot create duplicate active records.
- **Alternatives considered**: In-memory Redis locking on URL (adds unnecessary complexity when database constraint already provides transactional guarantees).

## Risks / Trade-offs

- **[Risk] Vector Store Disconnect during Deletion**: If Qdrant is unavailable when `DELETE /documents/{doc_id}` is requested, vectors might remain orphaned.
  - *Mitigation*: The delete endpoint first invokes `vector_store.delete_by_doc_id(doc_id)`. If Qdrant raises an error, the database record is not soft-deleted, and an HTTP 500/502 error is returned, ensuring data consistency across both stores.
- **[Risk] Malformed or Non-Web URLs in Ingest Requests**: Invalid URL formats could cause downstream worker failures.
  - *Mitigation*: Validate URLs using Pydantic's `HttpUrl` type in `IngestRequest` to fail fast at the API boundary with HTTP 422.
