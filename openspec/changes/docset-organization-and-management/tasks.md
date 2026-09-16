## 1. Data Models & Database Migration

- [x] 1.1 Create `Docset` SQLModel entity in `app/models/docset.py` with `name`, `document_count`, `created_at`, `updated_at`, and `deleted_at`.
- [x] 1.2 Update `Document` SQLModel in `app/models/document.py` to include `docset` column and composite unique index on `(docset, source_url)` where `deleted_at IS NULL`.
- [x] 1.3 Create Alembic migration script creating `docsets` table, seeding the protected `"default"` docset, populating existing documents, and updating unique constraints.
- [x] 1.4 Add unit tests for `Docset` model and updated `Document` model behavior in `tests/test_models.py`.


## 2. Qdrant Vector Storage Enhancements

- [x] 2.1 Update `QdrantVectorStore` in `app/services/vector_store/qdrant.py` to ensure keyword index on `docset` during collection initialization.
- [x] 2.2 Update `_build_point` to attach `docset` in point payloads alongside `doc_id`.
- [x] 2.3 Implement `delete_by_docset` method in `QdrantVectorStore` using Qdrant payload filter.
- [x] 2.4 Update `search` method to support optional `docset` filtering.
- [x] 2.5 Add unit tests in `tests/test_vector_store.py` for docset payload indexing, filtering, and bulk deletion.


## 3. Database Repository Layer

- [x] 3.1 Implement docset name normalization and validation helper (enforcing lowercase, 1-64 chars, `^[a-z0-9_-]+$`, and rejecting `"default"`).
- [x] 3.2 Update `check_active_url` and `create_batch_and_jobs` in `app/services/repository.py` to scope uniqueness and skipping to `(docset, source_url)`.
- [x] 3.3 Implement docset auto-creation and revival in `create_batch_and_jobs`.
- [x] 3.4 Implement soft-deleted document re-activation upon re-submission within the same docset.
- [x] 3.5 Implement `list_active_docsets` and `delete_docset` repository functions with auto-pruning.
- [x] 3.6 Update `list_indexed_documents` and `soft_delete_document` to be scoped to docset and trigger auto-pruning when remaining active document count reaches zero.
- [x] 3.7 Add comprehensive repository tests in `tests/test_repository.py`.

## 4. Pipeline Orchestration & Concurrency Guard

- [ ] 4.1 Update `IngestionPipelineService` in `app/services/pipeline.py` to pass `docset` down to vector store upsert.
- [ ] 4.2 Implement pre-upsert active check in `IngestionPipelineService` to halt execution and avoid ghost vector upserts if document or docset was deleted.
- [ ] 4.3 Update task dispatcher and worker signatures to pass `docset`.
- [ ] 4.4 Add unit tests in `tests/test_pipeline.py` for docset tagging and concurrent deletion guard.

## 5. REST API Schemas & Endpoints

- [ ] 5.1 Define Pydantic request/response schemas in `app/api/schemas.py` for docset listing (`DocsetListItemResponse`, `DocsetListResponse`) and docset deletion.
- [ ] 5.2 Implement `POST /docsets/{docset}/documents` batch ingestion endpoint with auto-creation and reserved-name validation.
- [ ] 5.3 Implement `GET /docsets` and `DELETE /docsets/{docset}` endpoints.
- [ ] 5.4 Implement `GET /docsets/{docset}/documents`, `GET /docsets/{docset}/documents/check`, and `DELETE /docsets/{docset}/documents/{doc_id}` endpoints.
- [ ] 5.5 Mount docsets router in `app/api/v1/router.py`.
- [ ] 5.6 Add comprehensive API endpoint tests in `tests/test_api_docsets.py`.

## 6. Verification & Documentation

- [ ] 6.1 Update `README.md` with new docset architecture, API endpoints, and curl examples.
- [ ] 6.2 Run full test suite with coverage enforcement (`pytest --cov=app --cov-report=term-missing --cov-fail-under=100`).
- [ ] 6.3 Run linting and format checks (`ruff check .`, `ruff format --check .`).
