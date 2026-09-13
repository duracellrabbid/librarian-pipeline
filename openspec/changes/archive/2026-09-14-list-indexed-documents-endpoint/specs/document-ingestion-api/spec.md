## ADDED Requirements

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
