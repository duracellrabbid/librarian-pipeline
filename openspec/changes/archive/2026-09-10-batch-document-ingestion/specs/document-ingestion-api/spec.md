## MODIFIED Requirements

### Requirement: Document Ingestion Submission
The system SHALL provide a `POST /documents/ingest` endpoint accepting a batch ingestion request payload containing an array of documents (each with a valid `url`, optional `title`, and optional `metadata`), subject to a configurable maximum batch size limit (`MAX_BATCH_INGEST_SIZE`).

#### Scenario: Successful batch ingestion submission
- **WHEN** a client submits a request payload containing one or more valid URLs within the configured batch limit
- **THEN** the system creates a `BatchIngestionJob` in `PENDING` state, creates `Document` and `IngestionJob` records linked to the batch for each accepted URL, enqueues background processing tasks, and returns HTTP 202 Accepted containing `main_job_id`, `status` (`PENDING`), `total_submitted`, `accepted_count`, and `skipped_count`.

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
- **WHEN** all URLs in a submitted batch are skipped due to intra-request duplicates or existing active status
- **THEN** the system records the batch with `accepted_count: 0`, dispatches zero worker jobs, and returns HTTP 202 Accepted with all skipped reasons.

### Requirement: Ingestion Job Status Monitoring
The system SHALL provide a `GET /documents/status/{main_job_id}` endpoint returning aggregated status, overall progress percentage, child job breakdowns, and skipped details for a batch ingestion job.

#### Scenario: Valid batch job status inquiry
- **WHEN** a client queries an existing `main_job_id`
- **THEN** the system returns HTTP 200 OK with `main_job_id`, aggregate `status` (`PENDING`, `PROCESSING`, `COMPLETED`, `PARTIALLY_FAILED`, or `FAILED`), `overall_progress_percentage`, `total_jobs`, `completed_jobs`, `failed_jobs`, a `jobs` array detailing each accepted document's current progress (`url`, `doc_id`, `status`, `progress_percentage`, `error_message`), and a `skipped` array detailing any skipped URLs and reasons.

#### Scenario: Non-existent batch job status inquiry
- **WHEN** a client queries a `main_job_id` that does not exist in the database
- **THEN** the system returns HTTP 404 Not Found.
