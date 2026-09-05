## Why

To expose the RAG ingestion pipeline to external clients and user interfaces, we need a clean, validated REST API. The API enforces key business constraints: asynchronous non-blocking job dispatching, rejection of duplicate active ingestions with HTTP 409, status polling, document existence verification, and safe soft-deletion paired with vector cleanup.

## What Changes

- Set up the FastAPI application with CORS, request logging, and global exception handlers.
- Configure dependency injection for database sessions, `TaskDispatcher`, and `QdrantVectorStore`.
- Implement the 4 core endpoints:
  1. `POST /documents/ingest`:
     - Checks if an active (non-deleted) document exists for the submitted URL.
     - If active: Returns `409 Conflict` ("URL already ingested. Delete existing document before re-ingesting.").
     - If not active: Creates `Document` and `IngestionJob`, dispatches background task via `TaskDispatcher`, returns `202 Accepted` with `job_id` and `doc_id`.
  2. `GET /documents/status/{job_id}`:
     - Returns `200 OK` with job progress, current status (`PENDING`, `SCRAPING`, etc.), and any error details.
  3. `GET /documents/check`:
     - Query parameter `?url=...` returning `200 OK` with `{ "exists": bool, "doc_id": Optional[UUID], "status": Optional[str] }`.
  4. `DELETE /documents/{doc_id}`:
     - Deletes all matching vectors from Qdrant by `doc_id`.
     - Soft-deletes the `Document` in PostgreSQL (`deleted_at = NOW()`).
     - Returns `200 OK`.
- Add integration test suite testing all endpoints against the test database and mocked/local services.

## Capabilities

### New Capabilities
- `document-ingestion-api`: FastAPI REST API providing ingestion submission, duplicate URL rejection, status tracking, existence checks, and soft-delete endpoints.

### Modified Capabilities
<!-- None -->

## Impact

- Provides the complete HTTP surface for the RAG ingestion pipeline.
- Delivers the user-facing deliverable for Wikipedia ingestion.
