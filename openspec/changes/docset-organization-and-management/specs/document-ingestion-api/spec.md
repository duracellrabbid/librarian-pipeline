## ADDED Requirements

### Requirement: Docset Listing
The system SHALL provide a `GET /docsets` endpoint returning a paginated list of all active docsets with metadata including normalized docset identifier, active document count, and audit timestamps. Docsets with zero active documents SHALL be automatically pruned and excluded from this listing.

#### Scenario: Successful docset listing
- **WHEN** a client issues a `GET /docsets` request with optional `limit` and `offset`
- **THEN** the system returns HTTP 200 OK containing `total`, `limit`, `offset`, and an items list of active docsets with `name`, `document_count`, `created_at`, and `updated_at`.

#### Scenario: Pruned empty docsets excluded
- **WHEN** a docset has zero active documents (either through deletion or never receiving accepted documents)
- **THEN** the system excludes that docset from the returned `GET /docsets` response.

### Requirement: Docset Deletion
The system SHALL provide a `DELETE /docsets/{docset}` endpoint that soft-deletes all active documents within the specified docset, prunes the docset, and purges all vector points in Qdrant associated with that docset in a single operation.

#### Scenario: Successful bulk deletion of a docset
- **WHEN** a client issues `DELETE /docsets/{docset}` for an active docset
- **THEN** the system soft-deletes all active `Document` records belonging to the docset, marks the docset pruned, purges all vectors in Qdrant matching the docset identifier, and returns HTTP 200 OK.

#### Scenario: Deletion of non-existent or already pruned docset
- **WHEN** a client issues `DELETE /docsets/{docset}` for a docset that does not exist or has no active documents
- **THEN** the system returns HTTP 404 Not Found.

## MODIFIED Requirements

### Requirement: Document Ingestion Submission
The system SHALL provide a `POST /docsets/{docset}/documents` endpoint accepting a batch ingestion request payload containing an array of documents (each with a valid `url`, optional `title`, and optional `metadata`), subject to a configurable maximum batch size limit (`MAX_BATCH_INGEST_SIZE`). The system SHALL normalize the `docset` identifier to lowercase and enforce naming constraints (1 to 64 alphanumeric characters, hyphens, and underscores). Ingestion into the reserved `"default"` docset SHALL be rejected. If the target docset does not exist or was previously pruned, it SHALL be automatically created or revived.

#### Scenario: Successful batch ingestion submission into docset
- **WHEN** a client submits a valid ingestion payload to `POST /docsets/{docset}/documents` for a valid non-default docset name
- **THEN** the system automatically creates or revives the docset if not present, creates a `BatchIngestionJob` in `PENDING` state, creates or re-activates `Document` and `IngestionJob` records linked to the docset and batch, enqueues background processing tasks, and returns HTTP 202 Accepted.

#### Scenario: Ingestion into reserved default docset rejected
- **WHEN** a client attempts to submit ingestion to `POST /docsets/default/documents` (or case variations such as `/docsets/DEFAULT/documents`)
- **THEN** the system rejects the request with HTTP 400 Bad Request or HTTP 422 Unprocessable Entity indicating that `"default"` is a reserved legacy docset.

#### Scenario: Invalid docset name formatting
- **WHEN** a client submits an ingestion request with an invalid docset identifier (longer than 64 characters or containing disallowed special characters)
- **THEN** the system rejects the request with HTTP 422 Unprocessable Entity.

#### Scenario: Disallowed domain URL skipping
- **WHEN** a client submits an ingestion request containing URLs that do not match the configured allowed domain prefix (e.g. `https://en.wikipedia.org`)
- **THEN** the system skips those URLs without failing the entire batch, records reason `domain_not_allowed` in `skipped` details, accepts any remaining valid URLs, and returns HTTP 202 Accepted.

#### Scenario: Batch size limit exceeded
- **WHEN** a client submits an ingestion request containing more documents than `MAX_BATCH_INGEST_SIZE`
- **THEN** the system rejects the request with HTTP 422 Unprocessable Entity.

#### Scenario: Intra-request duplicate URL handling
- **WHEN** a client submits an ingestion request containing duplicate URLs within the same request array
- **THEN** the system accepts the first occurrence, marks subsequent identical URLs as skipped with reason `duplicate_in_request`, and continues processing non-duplicate URLs.

#### Scenario: Active ingested or in-progress URL skipping within docset
- **WHEN** a client submits URLs where active documents already exist in the target docset with status `INDEXED` or an in-progress state (`PENDING`, `SCRAPING`, `CHUNKING`, `EMBEDDING`)
- **THEN** the system skips those URLs within this docset without failing the batch (recording reasons `already_ingested` or `currently_ingesting`), accepts any remaining valid URLs, and returns HTTP 202 Accepted.

#### Scenario: Identical URL accepted across different docsets
- **WHEN** a client submits a URL to `docset-b` that already exists and is `INDEXED` in `docset-a`
- **THEN** the system accepts the URL for `docset-b` as a completely independent document and dispatches an ingestion job.

#### Scenario: Re-activation of previously soft-deleted URL in docset
- **WHEN** a client submits a URL that was previously soft-deleted within the target docset
- **THEN** the system re-activates the existing document record (`deleted_at = NULL`), enqueues a new `IngestionJob`, and includes the document in `accepted_count`.

#### Scenario: Re-ingestion of previously failed URLs
- **WHEN** a client submits a URL whose latest ingestion job in the docset previously ended in `FAILED` status
- **THEN** the system accepts the URL for re-ingestion, creates a new `IngestionJob` linked to the batch, dispatches the job to the queue, and includes it in `accepted_count`.

#### Scenario: All submitted URLs skipped
- **WHEN** all URLs in a submitted batch are skipped due to intra-request duplicates, existing active status in the docset, or disallowed domains
- **THEN** the system records the batch with `accepted_count: 0`, dispatches zero worker jobs, and returns HTTP 202 Accepted with all skipped reasons.

### Requirement: Document Existence Verification
The system SHALL provide a `GET /docsets/{docset}/documents/check` endpoint accepting a `url` query parameter to check whether a URL is actively ingested within the specified docset.

#### Scenario: Active URL check within docset
- **WHEN** a client queries `GET /docsets/{docset}/documents/check?url={url}` for a URL actively ingested in that docset
- **THEN** the system returns HTTP 200 OK with `exists: true`, `doc_id`, and latest job `status`.

#### Scenario: Non-ingested or soft-deleted URL check within docset
- **WHEN** a client queries `GET /docsets/{docset}/documents/check?url={url}` for a URL that does not exist in that docset or has been soft-deleted
- **THEN** the system returns HTTP 200 OK with `exists: false`, `doc_id: null`, and `status: null`.

### Requirement: Document Soft Deletion and Vector Purging
The system SHALL provide a `DELETE /docsets/{docset}/documents/{doc_id}` endpoint to purge vector points from Qdrant and soft-delete the specified document in PostgreSQL. If the deleted document was the last active document in the docset, the system SHALL automatically prune the docset.

#### Scenario: Successful document deletion
- **WHEN** a client sends `DELETE /docsets/{docset}/documents/{doc_id}` for an active document belonging to the specified docset
- **THEN** the system deletes all vector points in Qdrant matching `doc_id`, marks the `Document` record soft-deleted (`deleted_at = NOW()`), prunes the docset if no active documents remain, and returns HTTP 200 OK.

#### Scenario: Deletion of non-existent or mismatched docset document
- **WHEN** a client sends `DELETE /docsets/{docset}/documents/{doc_id}` where the document does not exist, belongs to a different docset, or is already soft-deleted
- **THEN** the system returns HTTP 404 Not Found.

### Requirement: Indexed Documents Listing
The system SHALL provide a `GET /docsets/{docset}/documents` endpoint that retrieves a paginated list of actively indexed documents belonging to the specified docset.

#### Scenario: Listing indexed documents with default pagination
- **WHEN** a client issues a `GET /docsets/{docset}/documents` request without pagination parameters
- **THEN** the system returns HTTP 200 OK with total count, `limit: 20`, `offset: 0`, and an array of items containing only active documents with status `INDEXED` belonging to that docset.

#### Scenario: Listing indexed documents with custom pagination
- **WHEN** a client issues a `GET /docsets/{docset}/documents?limit=10&offset=5` request
- **THEN** the system returns HTTP 200 OK with a slice of at most 10 documents belonging to that docset starting from offset 5.

#### Scenario: Filtering indexed documents by URL or title
- **WHEN** a client issues a `GET /docsets/{docset}/documents?query=quantum` request
- **THEN** the system returns HTTP 200 OK containing only indexed documents in that docset whose `source_url` or `title` contains the search string (case-insensitive).

#### Scenario: Non-indexed and soft-deleted documents excluded
- **WHEN** documents exist in the docset with statuses other than `INDEXED` (e.g. `FAILED`, `PENDING`) or with a non-null `deleted_at` timestamp
- **THEN** the system excludes those documents from the returned listing.
