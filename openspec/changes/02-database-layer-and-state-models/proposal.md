## Why

An ingestion pipeline requires a persistent metadata store to track documents, enforce duplicate URL rejection rules, support non-destructive soft deletes, and maintain a state machine for asynchronous background jobs. Implementing a robust database schema with Alembic migrations ensures reproducible schema state and data integrity across all environments.

## What Changes

- Set up async database session management with SQLAlchemy / SQLModel for PostgreSQL.
- Configure Alembic for database migrations (`alembic init` + migration templates).
- Create `Document` model:
  - Fields: `id` (UUID), `source_type` (`url`, `pdf`, `text`), `source_url`, `content_hash`, `title`, `chunk_count`, `created_at`, `updated_at`, `deleted_at`.
  - Conditional unique index on `source_url` where `deleted_at IS NULL` to enforce duplicate rejection while allowing re-ingestion after soft delete.
- Create `IngestionJob` model:
  - Fields: `id` (UUID), `document_id` (foreign key), `status` (`PENDING`, `SCRAPING`, `CHUNKING`, `EMBEDDING`, `INDEXED`, `FAILED`), `error_message`, `progress_percentage`, `created_at`, `finished_at`.
- Implement database repository functions:
  - `check_active_url(url: str) -> Optional[Document]`
  - `create_document_and_job(...) -> (Document, IngestionJob)`
  - `update_job_status(...) -> IngestionJob`
  - `soft_delete_document(doc_id: UUID) -> Document`
- Create the baseline migration script and verify upgrade/downgrade against PostgreSQL.

## Capabilities

### New Capabilities
- `metadata-registry`: PostgreSQL data models, Alembic migrations, soft-delete mechanics, and active URL deduplication tracking.

### Modified Capabilities
<!-- None -->

## Impact

- Defines the persistent data contract for all downstream ingestion and API operations.
- Unblocks Phase 3 (Content Extractor and Chunking) and Phase 5 (Task Dispatcher).
