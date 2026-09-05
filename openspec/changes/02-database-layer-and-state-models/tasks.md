## 1. Database Infrastructure and Session Management

- [ ] 1.1 Write tests for async database engine and session dependency in `tests/test_db_session.py`
- [ ] 1.2 Implement async engine creation, session factory, and `get_async_session` dependency in `app/core/db.py`

## 2. SQLModel Entity Definitions

- [ ] 2.1 Write unit tests for `Document` model fields, defaults, relationships, and partial index in `tests/test_models.py`
- [ ] 2.2 Implement `Document` SQLModel with conditional unique index on active `source_url` in `app/models/document.py`
- [ ] 2.3 Write unit tests for `IngestionJob` model, status enum, validation, and relationships in `tests/test_models.py`
- [ ] 2.4 Implement `JobStatus` enum and `IngestionJob` SQLModel with foreign key linkage in `app/models/job.py` and register exports in `app/models/__init__.py`

## 3. Database Repository and State Transitions

- [ ] 3.1 Write tests for active URL deduplication and `check_active_url` in `tests/test_repository.py`
- [ ] 3.2 Implement `check_active_url` and `create_document_and_job` repository functions in `app/services/repository.py`
- [ ] 3.3 Write tests for job lifecycle transitions and timestamp updates in `tests/test_repository.py`
- [ ] 3.4 Implement `update_job_status` repository function handling progress and terminal timestamps in `app/services/repository.py`
- [ ] 3.5 Write tests for document soft deletion and subsequent re-ingestion behavior in `tests/test_repository.py`
- [ ] 3.6 Implement `soft_delete_document` repository function in `app/services/repository.py`

## 4. Alembic Migration Setup and Schema Verification

- [ ] 4.1 Initialize and configure `alembic.ini` and `alembic/env.py` with async support and `SQLModel.metadata`
- [ ] 4.2 Create baseline revision migration script for `documents` and `ingestion_jobs` tables and partial index
- [ ] 4.3 Verify migration upgrade (`alembic upgrade head`) and downgrade (`alembic downgrade base`) against PostgreSQL

## 5. Verification and Documentation

- [ ] 5.1 Run test suite, Ruff linting, and formatting checks to verify all tests pass cleanly
- [ ] 5.2 Update `README.md` with database layer architecture, state model diagrams, and migration instructions
