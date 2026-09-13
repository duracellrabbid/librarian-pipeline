## Context

See `proposal.md` for motivation. Currently, `app/api/v1/endpoints/documents.py` provides `POST /documents/ingest`, `GET /documents/status/{main_job_id}`, `GET /documents/check`, and `DELETE /documents/{doc_id}`. However, clients cannot retrieve a list of all actively ingested articles or URLs. PostgreSQL tracks all document lifecycle data, chunk counts, and job statuses, making it the ideal authoritative data source for this query.

## Goals / Non-Goals

**Goals:**
- Provide a paginated `GET /documents` endpoint returning only actively indexed documents (`JobStatus.INDEXED`, `deleted_at IS NULL`).
- Support case-insensitive search filtering across `title` and `source_url`.
- Support standard offset-based pagination (`limit`, `offset`) with a default limit of 20 and maximum of 100.
- Execute efficient single-roundtrip SQL queries avoiding N+1 database roundtrips.

**Non-Goals:**
- Direct scrolling of Qdrant vector points. Vector DB scroll queries are computationally heavy and lack relational sorting/filtering. PostgreSQL is the system of record.
- Full-text search engine integration. Substring matching (`ILIKE`) meets requirements with low cognitive complexity.

## Decisions

1. **Relational Query Strategy for Latest Job Status**
   - *Decision*: In `app/services/repository.py`, implement `list_indexed_documents`:
     - Construct a subquery selecting each document's latest ingestion job by `created_at`.
     - Filter `Document.deleted_at.is_(None)` and `IngestionJob.status == JobStatus.INDEXED.value`.
     - Apply optional substring search filter: `or_(Document.source_url.ilike(f"%{query}%"), Document.title.ilike(f"%{query}%"))`.
     - Execute a count query to obtain total matching documents and a paged query ordered by `Document.created_at.desc()`.
   - *Rationale*: Avoids N+1 queries while maintaining strict consistency with the job state machine.

2. **Endpoint Specification and Query Parameters**
   - *Decision*: Expose `GET /documents` on the existing `documents` router:
     - `limit: Annotated[int, Query(default=20, ge=1, le=100)]`
     - `offset: Annotated[int, Query(default=0, ge=0)]`
     - `query: Annotated[str | None, Query(default=None, description="Search term for URL or title")]`
   - *Rationale*: Standard REST convention consistent with existing endpoints in `app/api/v1/endpoints/documents.py`.

3. **Response Schema Design**
   - *Decision*: Define `DocumentListItemResponse` and `DocumentListResponse` in `app/api/schemas.py`:
     ```python
     class DocumentListItemResponse(BaseModel):
         id: UUID
         source_url: str
         title: str | None = None
         status: str = "indexed"
         chunk_count: int
         created_at: datetime
         updated_at: datetime


     class DocumentListResponse(BaseModel):
         total: int
         limit: int
         offset: int
         items: list[DocumentListItemResponse]
     ```
   - *Rationale*: Clean, self-describing pagination metadata compatible with OpenAPI documentation.

## Risks / Trade-offs

- **[Risk] Performance on large tables with substring `ILIKE`**: Large document registries might experience table scans on `ILIKE '%...%'`.
  - *Mitigation*: The `uq_documents_active_source_url` index already covers exact URL lookups; for typical RAG ingestion workloads, database volumes are well within performant limits. Future optimization can add trigram or pg_trgm indices if needed.
