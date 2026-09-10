# Loguru Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate application logging from Python's standard `logging` package to `loguru`, providing unified structured logging, contextual correlation tracking (`request_id` and `job_id`), dev/prod format differentiation, and an intercept handler for third-party libraries (Uvicorn, FastAPI, ARQ).

**Architecture:** A centralized logging module (`app/core/logging.py`) configures Loguru sinks based on runtime environment (`ENVIRONMENT`). A standard library `InterceptHandler` bridges Uvicorn, SQLAlchemy, and ARQ into Loguru. A FastAPI middleware intercepts requests to generate and bind `X-Request-ID` via `logger.contextualize()`, while ARQ worker tasks bind `job_id` and `doc_id`.

**Tech Stack:** Python 3.11+, Loguru (`>=0.7.2`), FastAPI, Uvicorn, ARQ, Pytest.

## Global Constraints

- Mandatory Test-Driven Development (Red-Green-Refactor).
- 100% statement coverage gate on `app` (`pytest --cov=app --cov-report=term-missing --cov-fail-under=100`).
- Strict linting and formatting compliance with Ruff (`ruff check .`, `ruff format --check .`).
- Low cognitive complexity ($\le 15$, aiming for $\le 10$).
- All updates must preserve existing endpoint contracts and database models.

---

### Task 1: Add Loguru Dependency and Core Logging Module

**Files:**
- Modify: `pyproject.toml`
- Create: `app/core/logging.py`
- Create: `tests/test_logging.py`

**Interfaces:**
- Produces:
  - `class InterceptHandler(logging.Handler)`: Standard library logging handler forwarding records to Loguru.
  - `def setup_logging() -> None`: Configures Loguru sinks and routes standard library loggers (`uvicorn`, `uvicorn.access`, `uvicorn.error`, `fastapi`, `arq`, `sqlalchemy`) through `InterceptHandler`.
  - `def format_record(record: dict) -> str`: Custom formatter for development console logs.

- [ ] **Step 1: Add loguru to pyproject.toml**
  Add `"loguru>=0.7.2"` to `dependencies` in `pyproject.toml`.

- [ ] **Step 2: Write failing tests for setup_logging and InterceptHandler**
  Create `tests/test_logging.py` testing:
  - `setup_logging` clears existing loguru handlers and registers stdout sink.
  - When `environment="production"`, output is serialized as JSON.
  - When `environment="development"`, output includes timestamp and colored level.
  - Standard library `logging.getLogger("test_logger").info("hello")` is intercepted and forwarded to Loguru.

- [ ] **Step 3: Run test to verify it fails (RED)**
  Run: `pytest tests/test_logging.py -v`
  Expected: ModuleNotFoundError or test failure.

- [ ] **Step 4: Implement app/core/logging.py (GREEN)**
  Implement `InterceptHandler` and `setup_logging()` respecting `settings.log_level` and `settings.environment`.

- [ ] **Step 5: Run tests to verify they pass**
  Run: `pytest tests/test_logging.py -v`
  Expected: PASS with 100% coverage on `app/core/logging.py`.

- [ ] **Step 6: Commit**
  ```bash
  git add pyproject.toml app/core/logging.py tests/test_logging.py
  git commit -m "feat(logging): add core loguru setup and stdlib intercept handler"
  ```

---

### Task 2: FastAPI Request Correlation ID Middleware & Main Integration

**Files:**
- Modify: `app/main.py`
- Modify: `tests/test_main.py`
- Modify: `tests/test_logging.py`

**Interfaces:**
- Consumes:
  - `setup_logging()` from `app.core.logging`
  - `from loguru import logger`
- Produces:
  - Request ID middleware binding `request_id` via `logger.contextualize(request_id=...)` and echoing `X-Request-ID` in HTTP response headers.

- [ ] **Step 1: Write failing test for Request ID correlation header and logging**
  In `tests/test_main.py`, add tests verifying:
  - Incoming request receives `X-Request-ID` header in response (retained if provided in request, or auto-generated UUID).
  - Logs emitted during request processing contain `request_id`.

- [ ] **Step 2: Run test to verify it fails (RED)**
  Run: `pytest tests/test_main.py -k "test_request_id" -v`
  Expected: FAIL (`X-Request-ID` header missing).

- [ ] **Step 3: Implement Request ID middleware and initialize setup_logging in app/main.py (GREEN)**
  - Call `setup_logging()` inside `create_app()` / `lifespan`.
  - Add `@application.middleware("http")` to extract/generate `X-Request-ID`, attach to response headers, and wrap call in `logger.contextualize(request_id=request_id)`.
  - Replace `import logging` and `logger = logging.getLogger(__name__)` with `from loguru import logger`.

- [ ] **Step 4: Run tests to verify they pass**
  Run: `pytest tests/test_main.py tests/test_logging.py -v`
  Expected: PASS.

- [ ] **Step 5: Commit**
  ```bash
  git add app/main.py tests/test_main.py tests/test_logging.py
  git commit -m "feat(api): integrate loguru and request correlation id middleware"
  ```

---

### Task 3: Migrate Services & Worker Tasks to Loguru with Context Binding

**Files:**
- Modify: `app/workers/tasks.py`
- Modify: `app/services/pipeline.py`
- Modify: `tests/test_pipeline_service.py`
- Modify: `tests/test_dispatcher.py`

**Interfaces:**
- Consumes: `from loguru import logger`
- Produces:
  - Contextual logging in `run_ingestion_task`: `logger.bind(job_id=..., doc_id=..., batch_id=...)`.
  - Structured pipeline logging in `IngestionPipelineService`.

- [ ] **Step 1: Write failing tests verifying context binding in tasks and pipeline**
  Add unit tests in `tests/test_dispatcher.py` / `tests/test_pipeline_service.py` confirming `run_ingestion_task` and `IngestionPipelineService` log with contextual fields.

- [ ] **Step 2: Run test to verify it fails (RED)**
  Run: `pytest tests/test_pipeline_service.py -v`

- [ ] **Step 3: Replace stdlib logging with loguru in pipeline and worker tasks (GREEN)**
  - In `app/workers/tasks.py`, replace `import logging` with `from loguru import logger`. Use `with logger.contextualize(job_id=str(job_id), ...):` during task execution.
  - In `app/services/pipeline.py`, replace `import logging` with `from loguru import logger`.

- [ ] **Step 4: Run full test suite to verify all green**
  Run: `pytest --cov=app --cov-report=term-missing --cov-fail-under=100`
  Expected: 100% statement coverage.

- [ ] **Step 5: Commit**
  ```bash
  git add app/workers/tasks.py app/services/pipeline.py tests/
  git commit -m "feat(workers): migrate worker tasks and pipeline service to loguru"
  ```

---

### Task 4: Documentation & Final Verification Gate

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README.md**
  - Update Architecture & Tech Stack section to reflect Loguru.
  - Add documentation for logging configuration, log formatting in development vs production, and request/job correlation IDs.

- [ ] **Step 2: Run complete lint, format, and coverage validation**
  ```bash
  ruff check .
  ruff format --check .
  pytest --cov=app --cov-report=term-missing --cov-fail-under=100
  ```

- [ ] **Step 3: Commit**
  ```bash
  git add README.md
  git commit -m "docs: update logging documentation for loguru migration"
  ```
