# metadata-registry Specification

## Purpose
Provides persistent metadata tracking, active URL deduplication, soft deletion, and job state machine management for ingested documents and background processing tasks.
## Requirements
### Requirement: Document Registration and Active URL Uniqueness
The system SHALL persist document metadata including source type, source URL, title, chunk count, content hash, and timestamp audit fields. The system SHALL enforce uniqueness of `source_url` among all active (non-deleted) documents.

#### Scenario: Registering a new document with a unique URL
- **WHEN** a document registration request is submitted with a valid source URL that does not exist among active documents
- **THEN** the system creates and persists the document record with active status and an assigned unique identifier

#### Scenario: Attempting to register an active duplicate URL
- **WHEN** a document registration request is submitted with a source URL that is already associated with an active document
- **THEN** the system rejects the registration request with a duplicate URL conflict error

#### Scenario: Registering a URL previously soft-deleted
- **WHEN** a document registration request is submitted with a source URL that belongs only to soft-deleted documents
- **THEN** the system accepts the registration and creates a new active document record with a distinct identifier

### Requirement: Document Soft Deletion
The system SHALL support non-destructive deletion of documents by marking them as deleted with a deletion timestamp. Soft-deleted documents SHALL be excluded from standard active document queries and active URL uniqueness constraints.

#### Scenario: Soft deleting an active document
- **WHEN** a deletion request is issued for an existing active document
- **THEN** the system records a deletion timestamp on the document record and retains the record and its associated history in the database

#### Scenario: Querying active documents
- **WHEN** documents are retrieved via active listing or lookup operations
- **THEN** documents containing a non-null deletion timestamp are excluded from the results

### Requirement: Ingestion Job State Lifecycle Management
The system SHALL track the state lifecycle of ingestion jobs associated with documents. The state machine SHALL support transitions across `PENDING`, `SCRAPING`, `CHUNKING`, `EMBEDDING`, `INDEXED`, and `FAILED` states, tracking progress percentage, error details upon failure, and completion timestamps.

#### Scenario: Initializing a new ingestion job
- **WHEN** a new ingestion process is initiated for a registered document
- **THEN** the system creates an ingestion job record linked to the document in the `PENDING` state with zero progress percentage and a creation timestamp

#### Scenario: Updating job progress and state
- **WHEN** an ongoing ingestion job progresses through stages (`SCRAPING`, `CHUNKING`, `EMBEDDING`)
- **THEN** the system updates the job state and records the current progress percentage

#### Scenario: Successful job completion
- **WHEN** all ingestion steps finish successfully
- **THEN** the system transitions the job state to `INDEXED`, sets progress percentage to 100, and records the finished timestamp

#### Scenario: Job failure with error recording
- **WHEN** an error occurs during any ingestion stage
- **THEN** the system transitions the job state to `FAILED`, persists the error message details, and records the finished timestamp

### Requirement: Reproducible Schema Migration
The system SHALL maintain a version-controlled, reproducible database schema management mechanism capable of applying upgrades to the latest schema version and cleanly reverting downgrades.

#### Scenario: Executing database migrations forward
- **WHEN** schema migration upgrades are applied against the database
- **THEN** all required tables, relationships, foreign keys, and conditional unique indices are created without error

#### Scenario: Reverting database migrations backward
- **WHEN** schema migration downgrade is applied to the baseline state
- **THEN** all created schema objects are reverted cleanly to their prior state

