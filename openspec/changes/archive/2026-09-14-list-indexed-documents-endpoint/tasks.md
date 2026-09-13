## 1. Schema and Repository Layer (TDD)

- [x] 1.1 Add failing unit tests in `tests/test_repository.py` for `list_indexed_documents` verifying:
  - Default pagination (returns at most 20 items, accurate total count)
  - Custom `limit` and `offset` slicing
  - Substring filtering by `source_url` and `title` (case-insensitive)
  - Exclusion of soft-deleted documents (`deleted_at IS NOT NULL`)
  - Exclusion of non-indexed documents (jobs in `PENDING`, `FAILED`, etc.)
- [x] 1.2 Define `DocumentListItemResponse` and `DocumentListResponse` Pydantic models in [app/api/schemas.py](file:///D:/Shared/rag-ingestion-pipeline/app/api/schemas.py#L149-L165).
- [x] 1.3 Implement `list_indexed_documents(session: AsyncSession, limit: int = 20, offset: int = 0, query: str | None = None) -> tuple[int, list[DocumentListItemResponse]]` in [app/services/repository.py](file:///D:/Shared/rag-ingestion-pipeline/app/services/repository.py#L380-L402) and verify repository tests pass.

## 2. API Endpoint Implementation (TDD)

- [x] 2.1 Add failing integration tests in `tests/test_documents_endpoints.py` for `GET /api/v1/documents` asserting:
  - 200 OK response with pagination metadata and items list
  - Pagination validation (`limit` between 1 and 100, `offset` >= 0)
  - Search filtering via `?query=...` query parameter
  - Correct exclusion of unindexed and deleted records
- [x] 2.2 Implement `GET /documents` endpoint in [app/api/v1/endpoints/documents.py](file:///D:/Shared/rag-ingestion-pipeline/app/api/v1/endpoints/documents.py#L100-L130) injecting `session` and calling `list_indexed_documents`.
- [x] 2.3 Verify all tests pass in `tests/test_documents_endpoints.py`.

## 3. Verification & Quality Gates

- [x] 3.1 Update [README.md](file:///D:/Shared/rag-ingestion-pipeline/README.md) to document the new `GET /api/v1/documents` endpoint with query parameters and example response payload.
- [x] 3.2 Run `ruff check .` and fix any linting or formatting issues.
- [x] 3.3 Run `pytest --cov=app --cov-report=term-missing --cov-fail-under=100` to verify 100% test statement coverage.
