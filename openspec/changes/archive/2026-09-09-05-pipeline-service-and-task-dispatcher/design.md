## Context

See `proposal.md` for motivation. In Phases 1 through 4, we built the foundational blocks: Docker infrastructure, PostgreSQL models/migrations, Crawl4AI web extraction, Hybrid Markdown chunking, Ollama `bge-m3` embedding client, and Qdrant vector storage. In Phase 5, we unite these isolated services into a cohesive asynchronous workflow orchestrated by `IngestionPipelineService` and driven by a background queue via an abstract `TaskDispatcher` protocol implemented with ARQ and Redis.

## Goals / Non-Goals

**Goals:**
- Define `TaskDispatcher` protocol in `app/core/dispatcher.py` to decouple task enqueueing from queue backend.
- Implement `ArqTaskDispatcher` in `app/workers/dispatcher.py` using `arq.create_pool` with Redis.
- Implement ARQ worker settings and task runner function in `app/workers/tasks.py`.
- Implement `IngestionPipelineService` in `app/services/pipeline.py` coordinating the full lifecycle:
  - Progress tracking (`PENDING` ➔ `SCRAPING` (20%) ➔ `CHUNKING` (40%) ➔ `EMBEDDING` (70%) ➔ `INDEXED` (100%)).
  - Injecting dependencies (`BaseExtractor`, `BaseChunker`, `BaseEmbeddingClient`, `BaseVectorStore`, and DB session).
  - Robust error handling: catches domain and unexpected exceptions, records `error_message`, and marks `FAILED`.
- Comprehensive unit and integration tests verifying pipeline orchestration, error recovery, and dispatcher integration with mocked Redis/services.

**Non-Goals:**
- REST API endpoint routing (deferred to Phase 6).
- Celery worker implementation (the architecture allows Celery as a drop-in adapter in the future, but ARQ is the immediate implementation).

## Decisions

### Decision: Decoupled `TaskDispatcher` Protocol
- **Rationale**: An abstract protocol (`TaskDispatcher`) ensures callers (FastAPI endpoints in Phase 6) remain decoupled from Redis or ARQ. If Celery or another task queue is adopted later, only the dispatcher adapter and worker entry point need replacement.
- **Alternatives considered**: Directly calling `arq_pool.enqueue_job()` inside route handlers (tightly couples HTTP layer to ARQ).

### Decision: Unified IngestionPipelineService Orchestrator
- **Rationale**: Keeps all business logic in a testable, framework-agnostic Python class. It receives components via dependency injection, making it trivial to unit test with mock extractors/embedders or run headlessly in scripts.
- **Alternatives considered**: Embedding the pipeline logic directly inside the ARQ worker task function (makes testing difficult and couples pipeline logic to the worker runtime).

### Decision: Granular Status Transitions and Progress Percentages
- **Rationale**: Updating the `IngestionJob` record at each milestone (`SCRAPING`, `CHUNKING`, `EMBEDDING`, `INDEXED`) with a percentage estimate gives clients actionable visibility when polling job status.
- **Alternatives considered**: Binary `PENDING` ➔ `INDEXED` without intermediate states (provides no visibility into where long-running jobs are spending time).

## Risks / Trade-offs

- **[Risk] ARQ Worker Process Crash**: If a worker process abruptly dies mid-job, the job could remain stuck in an intermediate status.
  - *Mitigation*: ARQ supports job timeouts and retry settings; future housekeeping or health check tasks can reap stalled jobs.
- **[Risk] Database Session Lifespan in Async Workers**: Long-running background tasks holding open database connections can exhaust pool connections.
  - *Mitigation*: The pipeline service manages DB sessions within context-managed scopes (`async with get_async_session() as session`), committing state updates at each stage rather than holding an open transaction throughout the entire scraping/embedding process.
