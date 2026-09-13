## ADDED Requirements

### Requirement: Indexed Document Retrieval and Counting
The system SHALL provide repository operations to query and count active documents that have successfully achieved `INDEXED` status, with optional substring filtering and offset-based pagination.

#### Scenario: Paged query for indexed documents
- **WHEN** the repository queries indexed documents with pagination parameters
- **THEN** it executes a paginated SQL query returning active documents whose latest job has status `INDEXED` ordered by creation time descending.

#### Scenario: Substring query filter on URL or title
- **WHEN** a search term is specified
- **THEN** the repository applies a case-insensitive `ILIKE` filter on `Document.source_url` and `Document.title`, returning matching items and accurate total match count.
