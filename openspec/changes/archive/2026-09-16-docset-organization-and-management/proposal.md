## Why

Currently, all ingested documents are stored in a single global namespace in PostgreSQL and indexed into Qdrant without semantic partitioning. When querying, retrieval spans the entire knowledge base, causing semantic collisions across disparate subject domains. Downstream clients cannot isolate documents by topic, project, or domain.

Introducing **Docsets** enables logical partitioning of documents and vector embeddings, scoped batch ingestion, domain-isolated listing and retrieval, and bulk lifecycle management (such as deleting an entire docset without impacting others).

## What Changes

- **Docset Organization & Scoped Ingestion**: Group ingested documents under human-readable, normalized docset identifiers (e.g. `python-docs`, `legal-contracts`, up to 64 alphanumeric characters, hyphens, and underscores).
- **Auto-Creation & Auto-Pruning**: Docsets are automatically created on-the-fly upon document ingestion. When all documents in a docset are deleted, the docset is automatically pruned. If an ingestion request targets a pruned docset, it is seamlessly revived.
- **Docset-Scoped Document Uniqueness**: The uniqueness constraint on active documents shifts from `source_url` globally to `(docset, source_url)`. The same URL can exist across multiple docsets independently.
- **Re-activation on Re-submission**: If a soft-deleted document is re-submitted to the same docset, it is re-activated (`deleted_at = NULL`) and re-indexed.
- **Protected Legacy Default Docset**: Pre-existing unassigned documents are migrated to a protected dummy docset named `default`. Ingesting new documents into `default` is strictly rejected as a reserved keyword.
- **Docset & Document REST Endpoints**:
  - `GET /docsets`: List all active docsets with document counts and timestamps.
  - `POST /docsets/{docset}/documents`: Ingest a batch of URLs into the specified docset.
  - `GET /docsets/{docset}/documents`: List paginated indexed documents in a docset with URL/title substring search.
  - `GET /docsets/{docset}/documents/check?url=...`: Check whether a URL is actively indexed in the specified docset.
  - `DELETE /docsets/{docset}/documents/{doc_id}`: Soft-delete a document and purge its vectors; prune the docset if it was the last active document.
  - `DELETE /docsets/{docset}`: Soft-delete all documents in the docset, prune the docset, and purge all Qdrant vectors matching the docset.
- **Guarded Vector Upsert**: Background worker pipeline validates that a document has not been deleted before upserting vectors into Qdrant to prevent ghost/orphan vectors from concurrent deletions.
- **Qdrant Vector Payload Indexing**: Store normalized `docset` in vector point payloads with a dedicated keyword index for filtered nearest-neighbor search.

## Capabilities

### Modified Capabilities
- `document-ingestion-api`: Add docset-scoped batch ingestion, docset listing, docset-scoped document listing, URL checking, and single/bulk deletion endpoints.
- `metadata-registry`: Support `Docset` entity / scoped document uniqueness `(docset, source_url)`, legacy `default` seeding, auto-pruning, re-activation, and docset queries.
- `qdrant-vector-store`: Add `docset` payload indexing, docset-filtered vector querying, and bulk vector deletion by docset identifier.
- `ingestion-pipeline-service`: Enrich chunk points with docset metadata and enforce active-status guards prior to vector upsert.

## Impact

- **API Routes**: Adds `/docsets` route tree in `app/api/v1/endpoints/docsets.py` (or refactored documents router), with updated request/response schemas.
- **Database Schema**: Adds `docsets` table or foreign key / column on `documents` table with Alembic migration for legacy rows; updates unique constraint.
- **Vector Storage**: Updates Qdrant point schema to include `docset` and adds Qdrant payload index for `docset`.
- **Worker & Pipeline**: Updates `IngestionPipelineService` and dispatcher to carry docset context and check cancellation/deletion status before Qdrant upsert.
