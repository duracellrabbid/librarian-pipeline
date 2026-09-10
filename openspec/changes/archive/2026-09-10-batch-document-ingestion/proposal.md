## Why

The current document ingestion endpoint only supports ingesting a single URL per request. In real-world workflows, clients often need to submit dozens or hundreds of URLs simultaneously. Forcing clients to submit individual requests increases network overhead, makes client-side job tracking cumbersome, and prevents coordinated batch progress monitoring. 

Enabling batch ingestion allows clients to submit multiple URLs in a single request with batch-size safeguards, automatic deduplication against existing ingested records and within the batch, and unified status polling via a single main job ID.

## What Changes

- **BREAKING**: Modify `POST /documents/ingest` request payload from single `{"url": "...", "title": "..."}` to an object containing an array of documents `{"documents": [{"url": "...", "title": "...", "metadata": {...}}, ...]}`.
- **BREAKING**: Modify `POST /documents/ingest` response to return only the `main_job_id`, initial batch status (`PENDING`), total submitted count, accepted count, and skipped count. Child job IDs are no longer directly returned to clients.
- **BREAKING**: Modify `GET /documents/status/{main_job_id}` to track ingestion progress via the `main_job_id`. The response returns aggregate batch progress and status alongside the individual breakdown of all child jobs and skipped URLs.
- Add pre-flight status validation and deduplication:
  - Deduplicate URLs within the incoming request payload (keeping the first occurrence and skipping subsequent ones as `duplicate_in_request`).
  - Check active documents in the database: skip URLs with latest job status in `INDEXED` (`already_ingested`) or `PENDING`/`SCRAPING`/`CHUNKING`/`EMBEDDING` (`currently_ingesting`).
  - Re-ingest URLs that previously `FAILED` or do not exist (or were soft-deleted).
  - Proceed with ingesting all valid non-skipped URLs.
- Introduce `MAX_BATCH_INGEST_SIZE` configuration setting (default: 10) in application settings and `.env`, rejecting requests with HTTP 422 if the document array exceeds the limit.
- Introduce a dedicated `BatchIngestionJob` model and table with relational foreign key linking `ingestion_jobs.batch_id` to maintain batch lifecycle state and skipped URL records.

## Capabilities

### New Capabilities
<!-- None -->

### Modified Capabilities
- `document-ingestion-api`: Update document ingestion submission requirement to accept an array of documents up to a configurable batch size, return a single main job ID, selectively skip already-ingested or currently-ingesting URLs while re-ingesting failed URLs, and update status monitoring to query and aggregate progress by main job ID.

## Impact

- **API Endpoints**: `POST /documents/ingest` and `GET /documents/status/{main_job_id}` in `app/api/v1/endpoints/documents.py`.
- **API Schemas**: `app/api/schemas.py` updated with `DocumentIngestItem`, `BatchIngestRequest`, `BatchIngestResponse`, `ChildJobStatusResponse`, `SkippedDocumentItem`, and updated `JobStatusResponse`.
- **Database Models**: New `BatchIngestionJob` model in `app/models/job.py` (or `app/models/batch_job.py`); new column `batch_id` on `IngestionJob`.
- **Database Migrations**: New Alembic migration script adding `batch_ingestion_jobs` and `ingestion_jobs.batch_id`.
- **Repository Layer**: `app/services/repository.py` updated with batch creation, pre-flight status checking, and batch status querying functions.
- **Configuration**: `app/core/config.py` and `.env.example` updated with `MAX_BATCH_INGEST_SIZE`.
- **Tests**: `tests/test_api_schemas.py`, `tests/test_api_endpoints.py`, and `tests/test_api_integration.py` updated to reflect batch contracts.
