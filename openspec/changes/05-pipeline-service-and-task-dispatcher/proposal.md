## Why

The core ingestion process involves multiple compute- and network-heavy steps (web scraping, text chunking, dense vector embedding, and multi-database writes). To keep client interactions responsive, this execution must run asynchronously in the background. Furthermore, wrapping the queue behind a clean `TaskDispatcher` interface ensures we can switch from ARQ to Celery in the future without modifying any business logic.

## What Changes

- Implement `IngestionPipelineService` containing the pure business logic:
  - Updates job status sequentially: `PENDING` ➔ `SCRAPING` ➔ `CHUNKING` ➔ `EMBEDDING` ➔ `INDEXED`.
  - Catches failures at any stage, logging the traceback and setting status to `FAILED` with `error_message`.
  - Updates the `Document` record with extracted title, final `chunk_count`, and sets `finished_at`.
- Define `TaskDispatcher` abstract protocol:
  - `enqueue_ingestion_job(job_id: UUID, doc_id: UUID, url: str) -> None`
- Implement `ArqTaskDispatcher` and ARQ worker task function:
  - Integrates natively with `asyncio` and Redis.
  - Registers the worker lifecycle and error listeners.
- Add headless end-to-end tests validating a full background run from task dispatch to final database status.

## Capabilities

### New Capabilities
- `task-dispatcher`: Decoupled queue dispatching protocol with ARQ Redis implementation.
- `ingestion-pipeline-service`: Multi-step stateful orchestration service connecting extraction, chunking, embedding, and storage.

### Modified Capabilities
<!-- None -->

## Impact

- Provides the complete headless background processing engine.
- Leaves the upcoming API layer as a thin HTTP translation layer.
