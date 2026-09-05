## Context

See `proposal.md` for motivation. The project currently possesses settings configuration in `app/core/config.py` defining PostgreSQL credentials (`database_url` with asyncpg driver and `sync_database_url` with psycopg/standard driver). The `app/models/` package is currently empty with only an `__init__.py`. We need an async SQLAlchemy/SQLModel database session management layer, entity models for `Document` and `IngestionJob`, database repository access functions, and an Alembic migration environment with a baseline migration.

## Goals / Non-Goals

**Goals:**
- Provide an async session factory and FastAPI dependency for PostgreSQL using `SQLModel` and `asyncpg`.
- Define `Document` and `IngestionJob` models with appropriate types, foreign keys, cascade rules, and partial indices.
- Implement a partial unique index on `documents (source_url) WHERE deleted_at IS NULL` to enforce active URL deduplication while allowing re-ingestion after soft deletion.
- Define a robust job state machine (`PENDING`, `SCRAPING`, `CHUNKING`, `EMBEDDING`, `INDEXED`, `FAILED`) with progress tracking and completion timestamps.
- Implement isolated async repository functions for document registration, duplicate URL checks, status updates, and soft deletion.
- Set up Alembic migration infrastructure with `alembic.ini` and async-compatible `env.py` to manage database schema evolution.

**Non-Goals:**
- Building REST API endpoints or FastAPI routing (deferred to Phase 6 `06-rest-api-endpoints`).
- Implementing background worker logic or Redis job dispatchers (deferred to Phase 5 `05-pipeline-service-and-task-dispatcher`).
- Direct integration with Crawl4AI or Qdrant vector storage (handled in subsequent phases).

## Decisions

### 1. SQLModel over Plain SQLAlchemy Core / Raw SQL
- **Decision**: Use `SQLModel` (combining Pydantic v2 and SQLAlchemy Core/ORM) for model definitions.
- **Rationale**: Provides automatic validation, seamless integration with FastAPI response/request models, and clean async session support with SQLAlchemy 2.0 style queries.
- **Alternatives Considered**: 
  - Raw `SQLAlchemy ORM`: Requires duplicate Pydantic schema declarations.
  - Raw `asyncpg` queries: Lacks declarative schema definitions, migration autogeneration, and relationship handling.

### 2. Partial Unique Index for Active URL Deduplication
- **Decision**: Define a conditional unique index:
  `Index("uq_documents_active_source_url", "source_url", unique=True, postgresql_where=text("deleted_at IS NULL"))`.
- **Rationale**: Enforces URL uniqueness at the database level strictly for active documents without interfering with historical records of soft-deleted documents.
- **Alternatives Considered**:
  - Application-level check only: Vulnerable to race conditions under concurrent ingestion requests.
  - Standard unique index on `(source_url, deleted_at)`: In PostgreSQL, `NULL != NULL`, so multiple records with `deleted_at IS NULL` would bypass standard compound unique constraints unless handled with complex triggers or non-standard sentinel values.

### 3. Separation of Session Lifecycle and Repository Layer
- **Decision**: Keep database session dependency injection (`get_async_session`) decoupled from repository functions. Repository functions will accept `session: AsyncSession` as an argument.
- **Rationale**: Enables composable transactions across multiple repository operations, simplifies unit and integration testing with test database sessions, and prevents hidden commit side-effects.
- **Alternatives Considered**:
  - Active Record pattern inside models: Couples entities directly to active sessions and makes unit testing difficult.

### 4. Async-Aware Alembic Migration Environment
- **Decision**: Configure `alembic/env.py` to use `async_engine_from_config` and `connection.run_sync` pointing to `SQLModel.metadata`.
- **Rationale**: Ensures migrations can be executed consistently using the application's async database URL or synchronous runner without driver mismatch.
- **Alternatives Considered**:
  - Pure synchronous Alembic with `psycopg2`: Requires adding an additional synchronous driver dependency when `asyncpg` and standard connection URLs can be used via `run_sync`.

## Risks / Trade-offs

- **[Risk] SQLite in-memory test compatibility with PostgreSQL-specific partial indices** → **Mitigation**: Use Postgres for integration testing via Docker Compose or configure index definition `postgresql_where` which SQLite safely ignores during local mock tests, while verifying migration against actual PostgreSQL.
- **[Risk] Unhandled session rollback on repository error** → **Mitigation**: Structure session dependency context manager (`get_async_session`) to catch exceptions, automatically rollback transactions, and re-raise.
- **[Risk] Concurrent job status update race conditions** → **Mitigation**: Use atomic SQL UPDATE statements in `update_job_status` and update audit fields (`updated_at`, `finished_at`) synchronously in the transaction.

## Migration Plan

1. Initialize Alembic configuration structure (`alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`).
2. Generate baseline migration `alembic/versions/0001_initial_metadata_schema.py` covering `documents` and `ingestion_jobs`.
3. Apply migration using `alembic upgrade head`.
4. Verify rollback capability using `alembic downgrade base` and re-apply `alembic upgrade head`.
