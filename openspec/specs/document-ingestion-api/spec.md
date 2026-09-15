# document-ingestion-api Specification

## Purpose
Defines the REST API endpoints and behavioral contracts for document ingestion submission, progress monitoring, existence checks, and soft deletion with vector purging.
## Requirements
### Requirement: Document Ingestion Submission
The system SHALL provide a `POST /documents/ingest` endpoint accepting a batch ingestion request payload containing an array of documents (each with a valid `url`, optional `title`, and optional `metadata`), subject to a configurable maximum batch size limit (`MAX_BATCH_INGEST_SIZE`).

#### Scenario: Successful batch ingestion submission
- **WHEN** a client submits a request payload containing one or more valid URLs within the configured batch limit
- **THEN** the system creates a `BatchIngestionJob` in `PENDING` state, creates `Document` and `IngestionJob` records linked to the batch for each accepted URL, enqueues background processing tasks, and returns HTTP 202 Accepted containing `main_job_id`, `status` (`PENDING`), `total_submitted`, `accepted_count`, and `skipped_count`.

#### Scenario: Disallowed domain URL skipping
- **WHEN** a client submits an ingestion request containing URLs that do not match the configured allowed domain prefix (e.g. `https://en.wikipedia.org`)
- **THEN** the system skips those URLs without failing the entire batch, records reason `domain_not_allowed` in `skipped` details, accepts any remaining valid URLs, and returns HTTP 202 Accepted.

#### Scenario: Batch size limit exceeded
- **WHEN** a client submits an ingestion request containing more documents than `MAX_BATCH_INGEST_SIZE`
- **THEN** the system rejects the request with HTTP 422 Unprocessable Entity.

#### Scenario: Intra-request duplicate URL handling
- **WHEN** a client submits an ingestion request containing duplicate URLs within the same request array
- **THEN** the system accepts the first occurrence, marks subsequent identical URLs as skipped with reason `duplicate_in_request`, and continues processing non-duplicate URLs.

#### Scenario: Active ingested or in-progress URL skipping
- **WHEN** a client submits URLs where active documents already exist with status `INDEXED` or an in-progress state (`PENDING`, `SCRAPING`, `CHUNKING`, `EMBEDDING`)
- **THEN** the system skips those URLs without failing the batch (recording reasons `already_ingested` or `currently_ingesting`), accepts any remaining valid URLs, and returns HTTP 202 Accepted.

#### Scenario: Re-ingestion of previously failed URLs
- **WHEN** a client submits a URL whose latest ingestion job previously ended in `FAILED` status
- **THEN** the system accepts the URL for re-ingestion, creates a new `IngestionJob` linked to the batch, dispatches the job to the queue, and includes it in `accepted_count`.

#### Scenario: All submitted URLs skipped
- **WHEN** all URLs in a submitted batch are skipped due to intra-request duplicates, existing active status, or disallowed domains
- **THEN** the system records the batch with `accepted_count: 0`, dispatches zero worker jobs, and returns HTTP 202 Accepted with all skipped reasons.

### Requirement: Ingestion Job Status Monitoring
The system SHALL provide a `GET /documents/status/{main_job_id}` endpoint returning aggregated status, overall progress percentage, child job breakdowns, and skipped details for a batch ingestion job.

#### Scenario: Valid batch job status inquiry
- **WHEN** a client queries an existing `main_job_id`
- **THEN** the system returns HTTP 200 OK with `main_job_id`, aggregate `status` (`PENDING`, `PROCESSING`, `COMPLETED`, `PARTIALLY_FAILED`, or `FAILED`), `overall_progress_percentage`, `total_jobs`, `completed_jobs`, `failed_jobs`, a `jobs` array detailing each accepted document's current progress (`url`, `doc_id`, `status`, `progress_percentage`, `error_message`), and a `skipped` array detailing any skipped URLs and reasons.

#### Scenario: Non-existent batch job status inquiry
- **WHEN** a client queries a `main_job_id` that does not exist in the database
- **THEN** the system returns HTTP 404 Not Found.

### Requirement: Document Existence Verification
The system SHALL provide a `GET /documents/check` endpoint accepting a `url` query parameter to check whether a URL is actively ingested.

#### Scenario: Active URL check
- **WHEN** a client queries `GET /documents/check?url={url}` for an actively ingested URL
- **THEN** the system returns HTTP 200 OK with `exists: true`, `doc_id`, and latest job `status`.

#### Scenario: Non-ingested or soft-deleted URL check
- **WHEN** a client queries `GET /documents/check?url={url}` for a URL that does not exist or has been soft-deleted
- **THEN** the system returns HTTP 200 OK with `exists: false`, `doc_id: null`, and `status: null`.

### Requirement: Document Soft Deletion and Vector Purging
The system SHALL provide a `DELETE /documents/{doc_id}` endpoint to purge vector points from Qdrant and soft-delete the document in PostgreSQL.

#### Scenario: Successful document deletion
- **WHEN** a client sends `DELETE /documents/{doc_id}` for an active document
- **THEN** the system deletes all vector points in Qdrant matching `doc_id`, marks the `Document` record soft-deleted (`deleted_at = NOW()`), and returns HTTP 200 OK.

#### Scenario: Deletion of non-existent or already deleted document
- **WHEN** a client sends `DELETE /documents/{doc_id}` for a document that does not exist or is already soft-deleted
- **THEN** the system returns HTTP 404 Not Found.

### Requirement: Indexed Documents Listing
The system SHALL provide a `GET /documents` endpoint that retrieves a paginated list of actively indexed documents from the system of record.

#### Scenario: Listing indexed documents with default pagination
- **WHEN** a client issues a `GET /documents` request without parameters
- **THEN** the system returns HTTP 200 OK with total count, `limit: 20`, `offset: 0`, and an array of items containing only active documents with status `INDEXED`.

#### Scenario: Listing indexed documents with custom pagination
- **WHEN** a client issues a `GET /documents?limit=10&offset=5` request
- **THEN** the system returns HTTP 200 OK with a slice of at most 10 documents starting from offset 5.

#### Scenario: Filtering indexed documents by URL or title
- **WHEN** a client issues a `GET /documents?query=quantum` request
- **THEN** the system returns HTTP 200 OK containing only indexed documents whose `source_url` or `title` contains the search string (case-insensitive).

#### Scenario: Non-indexed and soft-deleted documents excluded
- **WHEN** documents exist with statuses other than `INDEXED` (e.g. `FAILED`, `PENDING`) or with a non-null `deleted_at` timestamp
- **THEN** the system excludes those documents from the returned listing.

