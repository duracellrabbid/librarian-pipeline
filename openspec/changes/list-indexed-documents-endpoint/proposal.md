## Why

Currently, the REST API exposes endpoints to submit ingestion batches, check batch progress, check individual URL existence, and delete documents, but does not provide an endpoint to list or browse all documents actively ingested into the vector database. Downstream clients and administrators have no way to retrieve an overview or audit the list of available articles and URLs. Providing a dedicated listing endpoint backed by PostgreSQL with filtering and pagination fills this visibility gap.

## What Changes

- Implement `GET /documents` REST endpoint returning only actively indexed documents (`INDEXED` status, `deleted_at IS NULL`).
- Support pagination query parameters: `limit` (integer, default: 20, minimum: 1, maximum: 100) and `offset` (integer, default: 0, minimum: 0).
- Support search query filtering via an optional `query` parameter matching against document `title` or `source_url` (case-insensitive substring match).
- Return a structured response payload containing `total` count, `limit`, `offset`, and a list of `items` detailing document IDs, URLs, titles, chunk counts, statuses, and audit timestamps.
- Implement database repository queries in `app/services/repository.py` utilizing PostgreSQL as the authoritative source of truth.

## Capabilities

### Modified Capabilities
- `document-ingestion-api`: Add `GET /documents` endpoint supporting pagination and URL/title search filtering for indexed documents.
- `metadata-registry`: Add repository function `list_indexed_documents` to query and count active indexed documents with filtering and pagination.

## Impact

- **API Routes**: Adds `GET /documents` endpoint in `app/api/v1/endpoints/documents.py`.
- **API Schemas**: Introduces `DocumentListItemResponse` and `DocumentListResponse` in `app/api/schemas.py`.
- **Database Repository**: Adds `list_indexed_documents` in `app/services/repository.py` joining `Document` and `IngestionJob` on `JobStatus.INDEXED`.
