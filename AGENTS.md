# Agent Guidelines & Development Rules (`AGENTS.md`)

Welcome to the **RAG Ingestion Pipeline** repository. All AI assistants, autonomous agents, and developers contributing to this codebase must adhere to the workflows and standards outlined in this document.

---

## Core Development Rules

### 1. Test-Driven Development (TDD) is Mandatory
- **Presumed a Must:** Every feature, bugfix, or behavioral modification must follow the **Red-Green-Refactor** cycle.
- **Red:** Write a failing test first demonstrating the intended behavior or reproducing the bug. Verify that it fails for the expected reason.
- **Green:** Implement the minimum production code required to make the test pass.
- **Refactor:** Clean up and optimize while ensuring all tests remain green.
- **Iron Law:** No production code without a failing test first. Mocks should only be used when testing actual external boundary interfaces (network calls, external third-party services).

### 2. Dedicated Branch for Every Spec Change
- **Branch Isolation:** A new git branch **MUST** be created for every OpenSpec (or similar spec tooling) change before any implementation starts.
- **Branch Naming Convention:**
  - Feature changes: `feat/<change-name>` (e.g. `feat/02-database-layer-and-state-models`)
  - Fixes / refactors: `fix/<change-name>` or `refactor/<change-name>`
- **Workflow:**
  1. Create and switch to the branch: `git checkout -b feat/<change-name>`
  2. Implement tasks following TDD and verify all tests.
  3. Archive the spec change upon full completion and verification.
  4. Ensure all changes are committed cleanly to the branch.

### 3. README Updated with Every Change
- **Documentation Integrity:** Whenever a change introduces or modifies:
  - Backing services or local infrastructure (`docker-compose.yml`)
  - Configuration or environment variables (`.env.example`)
  - Application endpoints, services, or architecture components
  - CLI utilities or setup instructions
- The [`README.md`](file:///D:/Shared/rag-ingestion-pipeline/README.md) **MUST** be updated within the same change to keep documentation in sync with reality.

---

## Repository Architecture & Layout

```text
rag-ingestion-pipeline/
├── app/
│   ├── api/          # FastAPI routers, endpoints, and request/response schemas
│   ├── core/         # Settings, logging, shared utilities (Pydantic Settings)
│   ├── models/       # SQLModel database tables and domain entities
│   ├── services/     # Ingestion pipeline, crawl4ai extractors, chunkers
│   └── workers/      # ARQ task workers and job dispatchers
├── openspec/         # OpenSpec planning specifications, changes, and archive
│   ├── changes/      # Active and archived changes
│   └── specs/        # Canonical capability specifications
├── scripts/          # Operational scripts (e.g. check_env.py)
├── tests/            # Test suite (unit, integration, and regression tests)
├── docker-compose.yml# Local infrastructure (Postgres 16, Redis 7, Qdrant, Ollama)
├── pyproject.toml    # Project dependencies and packaging metadata
└── .env.example      # Reference environment variable definitions
```

---

## Technical Stack & Standards

- **Python:** `>=3.11` (Async-first using `asyncpg`, `asyncio`, `httpx`).
- **Web & API:** `FastAPI`, `Uvicorn`, `Pydantic v2`.
- **Database & State:** `SQLModel`, `Alembic`, `PostgreSQL 16`.
- **Background Jobs:** `ARQ`, `Redis 7`.
- **Vector Storage & LLM:** `Qdrant` (v1.9+), `Ollama` (`bge-m3` embedding model).
- **Web Scraping:** `crawl4ai`.
- **Type Annotations:** Full type hints required across all functions, classes, and method signatures.

---

## Common Commands & Workflows

### Environment Setup
```bash
# Activate virtual environment (Windows PowerShell)
.venv\Scripts\Activate.ps1

# Install package in editable mode with development dependencies
pip install -e ".[dev]"
```

### Starting Backing Infrastructure
```bash
# Start PostgreSQL, Redis, Qdrant, and Ollama in the background
docker compose up -d

# Verify connectivity of backing services
python scripts/check_env.py
```

### Running Tests
```bash
# Run entire test suite
pytest

# Run tests with verbose output
pytest -v

# Run specific test file
pytest tests/test_config.py
```

### Linting & Type Checking (Ruff)
```bash
# Run linting, isort, and type-checking rules
ruff check .

# Automatically fix lint issues and organize imports
ruff check --fix .

# Check formatting
ruff format --check .

# Auto-format codebase
ruff format .
```

### OpenSpec Workflow
```bash
# List active changes
openspec list

# Check change status and tasks
openspec status --change "<change-name>"

# Validate change artifacts
openspec validate "<change-name>"

# Archive completed change
openspec archive --yes "<change-name>"
```
