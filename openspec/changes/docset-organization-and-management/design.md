## Context

Currently, `Document` in PostgreSQL and point payloads in Qdrant do not distinguish between subject domains. Document URLs are globally unique across all active records, and vector search scans the entire `knowledge_base` collection.

Introducing Docsets requires modifications across the data model, database repository, worker pipeline, vector store adapter, and REST API routing layers. See `proposal.md` for background and motivation.

## Goals / Non-Goals

**Goals:**
- Partition documents and Qdrant vector points by a normalized, human-readable `docset` string (1 to 64 chars, `^[a-z0-9_-]+$`).
- Enforce composite uniqueness `(docset, source_url)` for active documents, allowing identical URLs across different docsets.
- Support auto-creation and revival of docsets upon document ingestion, and auto-pruning when active document count reaches zero.
- Support re-activating soft-deleted documents upon re-submission within the same docset.
- Provide dedicated REST endpoints for docset listing, scoped document listing, docset-scoped document check, single document deletion, and bulk docset deletion.
- Guard the worker pipeline against ghost vector upserts if a document or docset was deleted during async processing.
- Seed a protected legacy `"default"` docset for all existing data.

**Non-Goals:**
- Multi-tenant user authentication, RBAC, or team-level authorization.
- Hierarchical or nested docsets (e.g. `parent/child` namespaces).
- Content-hash sharing or deduplication across docsets (docsets maintain isolated lifecycles).

## Decisions

### 1. Data Model: Dedicated `Docset` Table & Scoped `Document` Relation

**Decision:** Create a first-class `Docset` entity in PostgreSQL (`app/models/docset.py`):
```python
class Docset(SQLModel, table=True):
    __tablename__ = "docsets"

    name: str = Field(primary_key=True, max_length=64, description="Normalized lowercase docset identifier")
    document_count: int = Field(default=0, ge=0, description="Active document count")
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    deleted_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), index=True)
```
Update `Document`:
- Add `docset: str = Field(index=True, nullable=False, foreign_key="docsets.name")`.
- Replace `uq_documents_active_source_url` index with `uq_documents_active_docset_source_url` on `(docset, source_url)` where `deleted_at IS NULL`.

*Alternatives considered:*
- *String column only without table:* Makes `GET /docsets` require slow `SELECT DISTINCT` scans, prevents storing aggregate stats, and makes auto-pruning lifecycle difficult to track.
- *UUID primary key with slug alias:* Adds unnecessary indirection when the human-readable slug itself is unique, normalized, and immutable per lifecycle.

### 2. Identifier Normalization & Validation

**Decision:** All incoming docset path parameters are normalized via a helper:
```python
def normalize_docset_name(raw: str) -> str:
    cleaned = raw.strip().lower()
    if not re.match(r"^[a-z0-9_-]{1,64}$", cleaned):
        raise HTTPException(status_code=422, detail="Invalid docset identifier format")
    if cleaned == "default":
        raise HTTPException(status_code=422, detail="'default' is a reserved legacy docset")
    return cleaned
```

### 3. Qdrant Vector Storage Schema & Bulk Operations

**Decision:**
- Add `docset: str` to the point payload in `QdrantVectorStore._build_point`.
- Initialize a `PayloadSchemaType.KEYWORD` index on `docset` during `initialize_collection()`.
- Add `delete_by_docset(docset: str) -> int` using Qdrant's filter selector:
  ```python
  points_selector = models.Filter(
      must=[models.FieldCondition(key="docset", match=models.MatchValue(value=docset))]
  )
  ```
- Support `docset: str | None = None` in `search()` query filter.

### 4. Concurrency Guard in Pipeline Worker

**Decision:** In `IngestionPipelineService._execute_pipeline()`, check document status in the database immediately before `_embed_and_index_chunks()`. If `Document.deleted_at is not None`, abort indexing and mark job cancelled/failed to prevent orphan vectors in Qdrant.

### 5. Migration Strategy for Legacy Data

**Decision:** Alembic migration performs:
1. Create `docsets` table.
2. Add `docset` column to `documents` (nullable initially).
3. Insert `Docset(name='default', document_count=<count of active documents>)`.
4. Run `UPDATE documents SET docset = 'default' WHERE docset IS NULL`.
5. Alter `docset` column on `documents` to `NOT NULL`.
6. Drop index `uq_documents_active_source_url` and create `uq_documents_active_docset_source_url`.

## Risks / Trade-offs

- **[Risk] Worker embeds and indexes into Qdrant after docset is deleted**  
  $\rightarrow$ *Mitigation:* The pre-upsert active check in `IngestionPipelineService` queries the database inside the scoped session to ensure `deleted_at IS NULL` before calling Qdrant upsert.

- **[Risk] High document count in bulk docset deletion blocking the request**  
  $\rightarrow$ *Mitigation:* PostgreSQL updates all records matching `docset == name` in a single `UPDATE` statement; Qdrant deletes points via payload filter in a single asynchronous call.

- **[Risk] Inadvertent creation of multiple docsets via differing casing**  
  $\rightarrow$ *Mitigation:* Strict normalization (`.strip().lower()`) applied at the API routing boundary ensures case-insensitivity.
