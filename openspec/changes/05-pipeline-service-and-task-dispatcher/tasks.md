## 1. Task Dispatcher & Worker Infrastructure

- [x] 1.1 Define `DispatcherError` domain exception in `app/core/exceptions.py`.
- [x] 1.2 Define `TaskDispatcher` abstract protocol in `app/core/dispatcher.py`.
- [x] 1.3 Implement `ArqTaskDispatcher` in `app/workers/dispatcher.py` to enqueue ingestion jobs onto Redis via ARQ pool.
- [x] 1.4 Implement ARQ worker task runner and worker configuration settings in `app/workers/tasks.py`.
- [x] 1.5 Write unit tests in `tests/test_dispatcher.py` verifying task dispatching, parameter serialization, and connection failure handling with mocked Redis/ARQ pool.

## 2. Ingestion Pipeline Service

- [x] 2.1 Implement `IngestionPipelineService` in `app/services/pipeline.py` with dependency-injected extractor, chunker, embedding client, vector store, and database session factory.
- [x] 2.2 Implement stepwise status transitions and progress percentage updates (`SCRAPING`, `CHUNKING`, `EMBEDDING`, `INDEXED`) during pipeline execution.
- [x] 2.3 Implement robust error capture ensuring any pipeline exception sets the job to `FAILED` with an informative `error_message`.
- [x] 2.4 Implement `Document` record finalization updating title, chunk count, and timestamps in PostgreSQL upon indexing completion.
- [x] 2.5 Write unit tests in `tests/test_pipeline_service.py` verifying successful end-to-end progression, individual stage failures, and database updates with mocked components.

## 3. Integration Testing & Documentation

- [x] 3.1 Write a headless integration test in `tests/test_pipeline_integration.py` verifying that the pipeline executes from job creation to database and vector store verification.
- [x] 3.2 Update `README.md` with instructions for running the ARQ worker (`arq app.workers.tasks.WorkerSettings`), dispatcher configuration, and pipeline lifecycle overview.
