## Context

Currently, the document ingestion API (`POST /documents/ingest`) accepts a single URL and creates a 1:1 `Document` and `IngestionJob` record. To scale ingestion throughput and improve client ergonomics, the API is transitioning to a batch ingestion architecture where clients submit an array of documents and track the batch via a single `main_job_id`. See `proposal.md` and `specs/document-ingestion-api/spec.md` for background and behavioral contracts.

## Goals / Non-Goals

**Goals:**
- Provide a unified batch ingestion API allowing up to `MAX_BATCH_INGEST_SIZE` (default: 10) documents per submission.
- Ensure only the `main_job_id` is exposed to external clients for lifecycle tracking, abstracting internal child jobs.
- Perform robust pre-flight checks: skip active indexed or currently-ingesting documents, re-ingest previously failed documents, and deduplicate identical URLs within the request.
- Provide aggregated status monitoring through `GET /documents/status/{main_job_id}` reporting overall progress and per-document outcomes.

**Non-Goals:**
- Modifying the underlying ARQ worker task (`run_ingestion_pipeline`) logic; workers continue to execute individual document pipelines independently in parallel.
- Introducing multi-node distributed locks; reliance on PostgreSQL unique partial index `uq_documents_active_source_url` handles concurrent ingestion attempts safely.
- Long-term batch archival or batch cancellation workflows.

## Decisions

### Decision 1: Dedicated `batch_ingestion_jobs` Table
- **Choice**: Introduce a separate `batch_ingestion_jobs` table and add `batch_id` (foreign key) to `ingestion_jobs`.
- **Rationale**: A dedicated table provides a clean home for batch-level lifecycle state, timestamps, counts, and skipped document details (stored as structured JSON). It maintains relational integrity between batches and their child jobs.
- **Alternatives Considered**: Adding an unindexed/unconstrained `batch_id` UUID directly to `ingestion_jobs` without a parent table. Rejected because if all submitted URLs in a request are skipped, zero `ingestion_jobs` rows would exist, losing tracking history and skipped reasons when the client polls `GET /documents/status/{main_job_id}`.

### Decision 2: Status Polling Strictly via `main_job_id`
- **Choice**: The client only receives `main_job_id`. The endpoint `GET /documents/status/{main_job_id}` queries the `BatchIngestionJob` and joins or queries its child `ingestion_jobs`.
- **Rationale**: Simplifies client integration. Rather than managing an array of job UUIDs, clients track a single submission identifier.
- **Alternatives Considered**: Exposing both child job IDs and the main job ID. Rejected per user requirement to simplify the external contract and prevent clients from directly checking child jobs.

### Decision 3: In-Memory Pre-filtering & Re-ingestion Policy
- **Choice**:
  1. Deduplicate within the payload by canonical string URL (retain first occurrence, record rest as `duplicate_in_request`).
  2. Check existing active documents in PostgreSQL:
     - If latest job is `INDEXED` -> skip (`already_ingested`).
     - If latest job is in `PENDING`, `SCRAPING`, `CHUNKING`, `EMBEDDING` -> skip (`currently_ingesting`).
     - If latest job is `FAILED` -> re-use existing `Document` record, spawn a new `IngestionJob` linked to the batch, and enqueue.
     - If no active document -> create new `Document` and `IngestionJob` linked to the batch, and enqueue.
- **Rationale**: Prevents redundant work on active documents while ensuring failed ingestions can be cleanly recovered without requiring manual soft-deletion first.

### Decision 4: Batch Lifecycle State Machine & Aggregation
- **Choice**: Calculate overall progress and state dynamically or periodically:
  - `PENDING`: All accepted child jobs are `PENDING`.
  - `PROCESSING`: At least one child job has begun processing (`SCRAPING`, `CHUNKING`, `EMBEDDING`).
  - `COMPLETED`: All accepted child jobs reached `INDEXED` (or if 0 accepted, all skipped).
  - `PARTIALLY_FAILED`: Mix of `INDEXED` and `FAILED` terminal states across child jobs.
  - `FAILED`: All accepted child jobs reached `FAILED`.
  - Overall progress percentage: Arithmetic mean of child job progress percentages (or 100% if all skipped).

### Decision 5: Configuration via Pydantic Settings
- **Choice**: Add `max_batch_ingest_size: int = Field(default=10, ge=1)` to `Settings` in `app/core/config.py`.
- **Rationale**: Enables environment-specific tuning (`MAX_BATCH_INGEST_SIZE=10`) while providing an out-of-the-box sensible default.

## Risks / Trade-offs

- **[Risk] Worker Queue Flooding** → Enqueueing hundreds of URLs could saturate Redis.
  *Mitigation*: Hard request validation enforces `len(payload.documents) <= settings.max_batch_ingest_size`.
- **[Risk] Intra-batch URL Duplication Race** → If duplicate URLs appear in the request array, naïve parallel insertion could trigger unique constraint collisions.
  *Mitigation*: Pre-flight filtering deduplicates the input array in Python memory before running database transactions.
- **[Risk] Inter-request Concurrent Race Condition** → Two concurrent batch requests submitting the same new URL simultaneously.
  *Mitigation*: PostgreSQL partial unique index `uq_documents_active_source_url` raises an integrity error, which repository catches and handles cleanly.

## Migration Plan

1. Generate and apply Alembic migration `0002_add_batch_ingestion_jobs.py` to create `batch_ingestion_jobs` and alter `ingestion_jobs` to add `batch_id`.
2. Update SQLModel entities in `app/models/job.py`.
3. Update repository queries, service dispatchers, API schemas, and endpoints.
4. Verify end-to-end test suite passes with 100% coverage.
