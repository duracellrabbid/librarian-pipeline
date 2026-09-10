## 1. Configuration and Data Model Setup

- [x] 1.1 Add `max_batch_ingest_size` setting to `app/core/config.py` (around line 25) with default `10`, and update `.env.example`
- [x] 1.2 Add `BatchIngestionJob` model and `batch_id` foreign key on `IngestionJob` in `app/models/job.py` (lines 30-44)
- [x] 1.3 Create Alembic migration `alembic/versions/0002_add_batch_ingestion_jobs.py` for `batch_ingestion_jobs` table and `ingestion_jobs.batch_id` column
- [x] 1.4 Write unit tests for `BatchIngestionJob` model and migrations in `tests/test_models.py` (or `tests/test_database.py`)


## 2. API Request and Response Schemas

- [x] 2.1 Update schemas in `app/api/schemas.py`:
  - Add `DocumentIngestItem` (`url: HttpUrl`, `title: str | None`, `metadata: dict | None`)
  - Update `IngestRequest` to contain `documents: list[DocumentIngestItem]` (replacing lines 11-22)
  - Update `IngestResponse` to return `main_job_id`, `status`, `total_submitted`, `accepted_count`, `skipped_count`, `message` (lines 24-39)
  - Add `ChildJobStatusResponse` and `SkippedDocumentItem`
  - Update `JobStatusResponse` to return `main_job_id`, `status`, `overall_progress_percentage`, `total_jobs`, `completed_jobs`, `failed_jobs`, `jobs`, `skipped` (lines 41-58)
- [x] 2.2 Update schema tests in `tests/test_api_schemas.py` (lines 17-60) for batch request validation, serialization, and response structures


## 3. Repository Layer Implementation

- [x] 3.1 Implement pre-flight status inspection and intra-request deduplication in `app/services/repository.py` (around line 38):
  - Deduplicate incoming URLs, preserving first occurrence and flagging subsequent as `duplicate_in_request`
  - Check active document status: skip `INDEXED` (`already_ingested`) and in-progress states (`currently_ingesting`)
  - Allow re-ingestion for `FAILED` jobs by creating a new `IngestionJob` linked to the existing `Document`
- [x] 3.2 Implement `create_batch_and_jobs` in `app/services/repository.py` to persist `BatchIngestionJob`, accepted `Document` and `IngestionJob` rows, and skipped metadata in a single transaction
- [x] 3.3 Implement `get_batch_job_status` in `app/services/repository.py` to fetch a `BatchIngestionJob`, its child `IngestionJob` records, and compute aggregate progress and lifecycle state
- [x] 3.4 Write unit tests in `tests/test_repository.py` covering batch creation, duplicate skipping, in-progress skipping, and failed re-ingestion


## 4. REST API Endpoints Update

- [x] 4.1 Update `POST /documents/ingest` in `app/api/v1/endpoints/documents.py` (lines 32-65):
  - Validate `len(payload.documents) <= settings.max_batch_ingest_size`, raising HTTP 422 if exceeded
  - Call repository `create_batch_and_jobs`
  - Dispatch accepted jobs via `dispatcher.enqueue_ingestion_job` concurrently
  - Return HTTP 202 `IngestResponse` with `main_job_id`
- [x] 4.2 Update `GET /documents/status/{main_job_id}` in `app/api/v1/endpoints/documents.py` (lines 67-91):
  - Retrieve batch status via repository
  - Return HTTP 200 `JobStatusResponse` or HTTP 404 if `main_job_id` does not exist
- [x] 4.3 Update endpoint unit tests in `tests/test_api_endpoints.py` (lines 77-150) covering batch ingestion, max size validation, intra-request duplicates, skipping active docs, and batch status polling
- [x] 4.4 Update integration tests in `tests/test_api_integration.py` for full batch lifecycle

## 5. Verification and Documentation

- [x] 5.1 Update `README.md` to document the batch ingestion payload, status response, and `MAX_BATCH_INGEST_SIZE` configuration
- [x] 5.2 Run `ruff check .` and `ruff format .` to maintain code standards
- [x] 5.3 Run full test suite with 100% coverage enforcement (`pytest --cov=app --cov-report=term-missing --cov-fail-under=100`)
