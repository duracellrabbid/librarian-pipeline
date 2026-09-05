# RAG Ingestion Pipeline

A modular, production-ready RAG ingestion pipeline on a single server, featuring asynchronous document processing, vector storage, and state tracking.

## Architecture & Tech Stack

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) & [Uvicorn](https://www.uvicorn.org/)
- **Configuration**: [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- **Database**: PostgreSQL 16 managed via [SQLModel](https://sqlmodel.tiangolo.com/) and [Alembic](https://alembic.sqlalchemy.org/)
- **Task Queue**: [ARQ](https://arq-docs.helpmanual.io/) & [Redis 7](https://redis.io/)
- **Vector Database**: [Qdrant](https://qdrant.tech/) (v1.9+)
- **Embeddings & LLM**: [Ollama](https://ollama.ai/) (`bge-m3`)
- **Extraction**: [crawl4ai](https://github.com/unclecode/crawl4ai)
- **Linter & Type Checking**: [Ruff](https://docs.astral.sh/ruff/)

---

## Directory Structure

```text
rag-ingestion-pipeline/
├── app/
│   ├── api/          # FastAPI routes, routers, and request/response models
│   ├── core/         # Core settings, logging, and application configuration
│   ├── models/       # Database tables and domain entities
│   ├── services/     # Ingestion logic, content extractors, chunkers
│   └── workers/      # ARQ async background task workers
├── openspec/         # OpenSpec planning specifications, active/archived changes
├── scripts/          # Operational utilities (e.g. check_env.py)
├── tests/            # Test suite (pytest)
├── docker-compose.yml# Local backing services
├── pyproject.toml    # Python project packaging and dependency specifications
└── .env.example      # Environment variable template
```

---

## Quickstart Guide

### 1. Environment Setup

Create and activate a Python 3.11+ virtual environment:

```bash
# Windows PowerShell
python -m venv .venv
.venv\Scripts\Activate.ps1

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -e ".[dev]"
```

### 2. Configure Environment

Copy the example environment file:

```bash
cp .env.example .env
```

### 3. Launch Local Infrastructure

Start PostgreSQL, Redis, Qdrant, and Ollama using Docker Compose:

```bash
docker compose up -d
```

Verify service connectivity:

```bash
python scripts/check_env.py
```

### 4. Running Tests & Quality Checks

Execute the test suite using `pytest`:

```bash
pytest
```

Run linting, formatting, and type annotation checks using `ruff`:

```bash
# Run linting and type-checking rules
ruff check .

# Check code formatting
ruff format --check .
```

---

## Development Guidelines

Please refer to [`AGENTS.md`](AGENTS.md) for development workflows, including:
- Mandatory **Test-Driven Development (TDD)**.
- Dedicated Git branch for every OpenSpec change.
- Updating `README.md` with every change.
