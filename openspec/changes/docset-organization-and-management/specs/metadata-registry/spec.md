## ADDED Requirements

### Requirement: Docset Management and Auto-Pruning Lifecycle
The system SHALL manage docset lifecycle records tracking normalized name, active document count, and audit timestamps. The system SHALL auto-create or revive a docset record when an ingestion job adds documents to it. When all active documents in a docset are soft-deleted, the docset SHALL be marked pruned and omitted from active listings. The system SHALL initialize a reserved `"default"` docset during migration to hold all pre-existing legacy documents.

#### Scenario: Auto-creating a new docset
- **WHEN** documents are registered for a previously non-existent docset identifier
- **THEN** the system persists a new active docset record with normalized lowercase name and initializes its document count.

#### Scenario: Reviving a pruned docset
- **WHEN** new documents are submitted to a docset that previously had all documents soft-deleted
- **THEN** the system revives the docset to active status and updates its active document count.

#### Scenario: Auto-pruning docset upon zero remaining active documents
- **WHEN** the last active document in a docset is soft-deleted
- **THEN** the system marks the docset as pruned so it is excluded from active docset queries.

#### Scenario: Seeding legacy default docset
- **WHEN** database migration executes
- **THEN** the system creates the `"default"` docset and associates all existing documents lacking a docset with `"default"`.

## MODIFIED Requirements

### Requirement: Document Registration and Active URL Uniqueness
The system SHALL persist document metadata including source type, source URL, title, chunk count, content hash, docset identifier, and timestamp audit fields. The system SHALL enforce composite uniqueness of `(docset, source_url)` among all active (non-deleted) documents.

#### Scenario: Registering a new document with a unique URL in a docset
- **WHEN** a document registration request is submitted with a source URL that does not exist among active documents in the target docset
- **THEN** the system creates and persists the document record with active status, associated docset, and an assigned unique identifier.

#### Scenario: Attempting to register an active duplicate URL in the same docset
- **WHEN** a document registration request is submitted with a source URL that is already associated with an active document in the same docset
- **THEN** the system rejects the registration request with a duplicate URL conflict error.

#### Scenario: Registering an identical URL in a different docset
- **WHEN** a document registration request is submitted with a source URL that exists actively in a different docset
- **THEN** the system accepts the registration and creates a new active document record independent of the other docset.

#### Scenario: Registering a URL previously soft-deleted in the same docset
- **WHEN** a document registration request is submitted with a source URL that was soft-deleted in the target docset
- **THEN** the system re-activates the existing document record (`deleted_at = NULL`), clears previous content hash/chunk count, and prepares it for re-indexing.

### Requirement: Document Soft Deletion
The system SHALL support non-destructive deletion of documents by marking them as deleted with a deletion timestamp. Soft-deleted documents SHALL be excluded from standard active document queries and active `(docset, source_url)` uniqueness constraints. If a soft-deleted document was the last active document in its docset, the docset SHALL be pruned.

#### Scenario: Soft deleting an active document
- **WHEN** a deletion request is issued for an existing active document
- **THEN** the system records a deletion timestamp on the document record, decrements the docset's active count, prunes the docset if count reaches zero, and retains the record in the database.

#### Scenario: Querying active documents
- **WHEN** documents are retrieved via active listing or lookup operations
- **THEN** documents containing a non-null deletion timestamp are excluded from the results.

### Requirement: Indexed Document Retrieval and Counting
The system SHALL provide repository operations to query and count active documents that have successfully achieved `INDEXED` status within a specified docset, with optional substring filtering and offset-based pagination.

#### Scenario: Paged query for indexed documents in a docset
- **WHEN** the repository queries indexed documents for a specific docset with pagination parameters
- **THEN** it executes a paginated SQL query returning active documents belonging to that docset whose latest job has status `INDEXED`, ordered by creation time descending.

#### Scenario: Substring query filter on URL or title within docset
- **WHEN** a search term is specified for a docset query
- **THEN** the repository applies a case-insensitive `ILIKE` filter on `Document.source_url` and `Document.title` scoped to that docset, returning matching items and accurate total match count.
