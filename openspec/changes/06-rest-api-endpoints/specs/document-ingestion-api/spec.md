## Purpose

Defines the REST API endpoints and behavioral contracts for document ingestion submission, progress monitoring, existence checks, and soft deletion with vector purging.

## ADDED Requirements

### Requirement: Document Ingestion Submission
The system SHALL provide a `POST /documents/ingest` endpoint accepting an ingestion request payload containing a valid `url` and optional metadata.

#### Scenario: Successful ingestion submission
- **WHEN** a client submits a valid URL that is not currently actively ingested
- **THEN** the system creates a `Document` record, initializes an `IngestionJob` in `PENDING` state, dispatches the job to the background task queue, and returns HTTP 202 Accepted with `job_id`, `doc_id`, and `status`.

#### Scenario: Duplicate active URL rejection
- **WHEN** a client submits a URL that already has an active (non-deleted) record in the database
- **THEN** the system rejects the request with HTTP 409 Conflict and an error message indicating the document already exists and must be deleted before re-ingesting.

### Requirement: Ingestion Job Status Monitoring
The system SHALL provide a `GET /documents/status/{job_id}` endpoint returning real-time status and progress information for an ingestion job.

#### Scenario: Valid job status inquiry
- **WHEN** a client queries an existing `job_id`
- **THEN** the system returns HTTP 200 OK with `job_id`, current `status` (`PENDING`, `SCRAPING`, `CHUNKING`, `EMBEDDING`, `INDEXED`, or `FAILED`), `progress_percentage`, and `error_message` (if any).

#### Scenario: Non-existent job status inquiry
- **WHEN** a client queries a `job_id` that does not exist in the database
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
