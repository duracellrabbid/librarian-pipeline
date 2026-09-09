## 1. FastAPI App Initialization & Schemas

- [x] 1.1 Define request and response Pydantic schemas in `app/api/schemas.py` (`IngestRequest`, `IngestResponse`, `JobStatusResponse`, `DocumentCheckResponse`, `DeleteResponse`).
- [x] 1.2 Implement API dependency injection helpers in `app/api/deps.py` for database sessions, `TaskDispatcher`, and `QdrantVectorStore`.
- [x] 1.3 Implement the FastAPI application in `app/main.py` configuring lifespan events, CORS middleware, exception handlers, and routing.
- [x] 1.4 Write unit tests in `tests/test_api_schemas.py` verifying request validation, URL parsing, and response serialization.

## 2. Document Endpoints Implementation

- [x] 2.1 Implement `POST /documents/ingest` in `app/api/v1/endpoints/documents.py` validating active URL duplication (returning HTTP 409 Conflict) or enqueueing the job (returning HTTP 202 Accepted).
- [x] 2.2 Implement `GET /documents/status/{job_id}` in `app/api/v1/endpoints/documents.py` returning job progress and status or HTTP 404 Not Found.
- [x] 2.3 Implement `GET /documents/check` in `app/api/v1/endpoints/documents.py` verifying whether a URL is currently active in the database.
- [x] 2.4 Implement `DELETE /documents/{doc_id}` in `app/api/v1/endpoints/documents.py` coordinating Qdrant vector deletion and PostgreSQL soft-deletion.
- [x] 2.5 Write unit tests in `tests/test_api_endpoints.py` using `httpx.AsyncClient` with mocked dependencies to test all 4 endpoints, status codes, and error cases.

## 3. Full Integration Testing & Documentation

- [x] 3.1 Write end-to-end integration tests in `tests/test_api_integration.py` verifying the complete HTTP workflow: existence check, ingestion submission, status inspection, duplicate rejection, and soft-deletion.
- [x] 3.2 Update `README.md` with complete API endpoint documentation, example `curl` commands, and instructions for running the web server (`uvicorn app.main.py:app`).
